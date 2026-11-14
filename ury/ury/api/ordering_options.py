"""Variants and toppings as the ordering page of the guests sees them (docs/design/self-order-options.md).

A variant (「にぎり（上）」) and a topping (「大盛り」) are dishes of their own on the menu, linked from a dish:
`POS Item Variants` (the grades list each other) and `Item Add On` (a dish lists its toppings). The guests are shown:

  * one card for a group of variants, the base (the dish of the group that was put on the menu first);
  * no card for a topping (it is chosen in the dialog of its dish);
  * in the dialog the grades and the toppings of the chosen grade.

`build_model` works the structure out from the menu once; the functions that answer a guest use it."""

from dataclasses import dataclass, field

import frappe

TOPPING_JOINER = "・"


@dataclass
class OptionModel:
    visible: set = field(default_factory=set)  # the dishes the guests are shown (「セルフオーダー可」)
    group_of: dict = field(default_factory=dict)  # a dish of a group of variants -> [the grades, the base first]
    addons: dict = field(default_factory=dict)  # a dish the guests are shown -> [its toppings that are on the menu]
    addon_items: set = field(default_factory=set)  # every topping of every dish of the menu (they have no card)

    def grades(self, code):
        return self.group_of.get(code) or [code]

    def has_group(self, code):
        return code in self.group_of

    def orderable_addons(self):
        """The toppings a guest may order: those of the dishes the guests are shown."""
        found = set()
        for toppings in self.addons.values():
            found.update(toppings)
        return found


def build_model(menu_name, full_codes, visible_codes):
    """`full_codes`: the dishes of the menu (the enabled ones); `visible_codes`: those among them that the guests are shown."""
    full, visible = set(full_codes), set(visible_codes)
    model = OptionModel(visible=visible)
    if not full:
        return model

    # plain queries: the menu is read for every card the guests see, and nothing here needs the documents
    order = {
        row.item: row.idx
        for row in frappe.db.sql("select item, idx from `tabURY Menu Item` where parent = %s", (menu_name,), as_dict=True)
    }

    # the grades: dishes joined by a link in either direction form a group (only the dishes the guests are shown)
    parent = {code: code for code in visible}

    def find(code):
        while parent[code] != code:
            parent[code] = parent[parent[code]]
            code = parent[code]
        return code

    if visible:
        for link in frappe.db.sql(
            "select parent, item from `tabPOS Item Variants` where parenttype = 'Item' and parent in %s",
            (tuple(visible),),
            as_dict=True,
        ):
            if link.item in visible:
                parent[find(link.item)] = find(link.parent)
    groups = {}
    for code in visible:
        groups.setdefault(find(code), []).append(code)
    for members in groups.values():
        if len(members) > 1:
            members.sort(key=lambda code: (order.get(code, 0), code))
            for code in members:
                model.group_of[code] = members

    # the toppings
    rows = frappe.db.sql(
        "select parent, item, idx from `tabItem Add On` where parenttype = 'Item' and parent in %s order by parent, idx",
        (tuple(full),),
        as_dict=True,
    )
    for row in rows:
        if row.item not in full:
            continue
        model.addon_items.add(row.item)
        if row.parent in visible:
            model.addons.setdefault(row.parent, []).append(row.item)
    return model


def label_of(name, owner_name):
    """What the dialog writes for a topping: its name without the 「dish・」 in front (the dish is named above it)."""
    prefix = f"{owner_name}{TOPPING_JOINER}"
    if owner_name and name.startswith(prefix) and len(name) > len(prefix):
        return name[len(prefix):]
    return name
