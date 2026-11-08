# Frappe leaves a field out of list queries when its name contains `_seen`

Found 2026-11-08 on Frappe **15.125.0** (`e7458ff`). To check when Frappe is upgraded, and to report upstream.

## What happens
`frappe.get_list`, `frappe.get_all`, the Desk lists and reports (`frappe.desk.reportview.get`) drop a field from the
`select` when its **name contains** `_user_tags`, `_comments`, `_assign`, `_liked_by` or `_seen` and the table has no
column of that exact name. A field `last_seen` is silently gone; no error, no log. `frappe.db.get_value` and direct SQL
are not affected, so code that only reads and writes the value works and the bug stays hidden.

Here it showed as the Desk list of the tablets (`URY Ordering Device`): every tablet red, "No report for 5 minutes",
while `last_seen` in the database was moving every few seconds.

## Where
`frappe/model/db_query.py`, `DatabaseQuery.set_optional_columns`:

```python
def set_optional_columns(self):
    """Removes optional columns like `_user_tags`, `_comments` etc. if not in table"""
    # remove from fields
    to_remove = []
    for fld in self.fields:
        to_remove.extend(fld for f in optional_fields if f in fld and f not in self.columns)   # <- substring test
```

`optional_fields = ("_user_tags", "_comments", "_assign", "_liked_by", "_seen")` (`frappe/model/__init__.py`). `f in fld`
is a substring test on the whole field (``"`tabDevice`.`last_seen`"``), not a comparison of the column name.

## How to reproduce
On a site, with a DocType that has a field `last_seen` (and no `_seen` column in its table):

```python
frappe.get_list("URY Ordering Device", fields=["name", "last_seen"], run=False)
# -> 'select `name`'          (last_seen is gone)
frappe.get_list("URY Ordering Device", fields=["*"])   # -> has last_seen: only the explicit field name is dropped
```

## What we did
- Renamed `last_seen` to `last_reported_at` (URY Ordering Device, URY Payment Terminal); patch `rename_last_seen`.
- `ury/ury/api/test_field_names.py` fails when a field name of ours contains one of the five strings.
- `TestWhatTheDeskListGets` (test_ordering_device.py) asks the Desk list API for the field over HTTP.
- CLAUDE.md: the rule for new fields.

## On an upgrade of Frappe
Check whether `set_optional_columns` still matches by substring (compare with the code above). If it compares the column
name, the rule in CLAUDE.md can go; the field names we renamed can stay. An upstream report would say: "get_list drops a
field whose name merely contains `_seen` (for example `last_seen`)".

`POS Invoice.custom_comments` contains `_comments` but is not dropped: the POS Invoice table has a `_comments` column
(Frappe adds it when the first comment is made, so this holds only as long as the column is there).
