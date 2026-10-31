import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Button, Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, Input } from '@ury/ui';
import { SearchableSelect } from '../../components/common/SearchableSelect';
import { useBranchContext } from '../../context/BranchContext';
import { t } from '../../i18n';

type ModalType = 'menu' | 'table' | 'room' | 'branch' | 'user' | null;

export const QuickActions: React.FC = () => {
  const navigate = useNavigate();
  const { refreshDashboard } = useBranchContext();
  const [activeModal, setActiveModal] = useState<ModalType>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Form states
  const [menuForm, setMenuForm] = useState({ name: '', course: 'Main Course', price: '' });
  const [tableForm, setTableForm] = useState({ name: '', seats: '4', room: 'Main Dining', shape: 'Square' });
  const [roomForm, setRoomForm] = useState({ name: '', type: 'AC', branch: 'Downtown Main' });
  const [branchForm, setBranchForm] = useState({ name: '', code: '', invoicePrefix: 'INV-' });
  const [userForm, setUserForm] = useState({ name: '', email: '', role: 'URY Cashier' });

  const showNotification = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3000);
  };

  const handleClose = () => {
    setActiveModal(null);
  };

  const handleSubmitMenu = (e: React.FormEvent) => {
    e.preventDefault();
    if (!menuForm.name || !menuForm.price) return;
    showNotification(t('dashboard.quick.menu_added', { name: menuForm.name }));
    setMenuForm({ name: '', course: 'Main Course', price: '' });
    handleClose();
    refreshDashboard();
  };

  const handleSubmitTable = (e: React.FormEvent) => {
    e.preventDefault();
    if (!tableForm.name) return;
    showNotification(t('dashboard.quick.table_added', { name: tableForm.name, seats: tableForm.seats }));
    setTableForm({ name: '', seats: '4', room: 'Main Dining', shape: 'Square' });
    handleClose();
    refreshDashboard();
  };

  const handleSubmitRoom = (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomForm.name) return;
    showNotification(t('dashboard.quick.zone_added', { name: roomForm.name }));
    setRoomForm({ name: '', type: 'AC', branch: 'Downtown Main' });
    handleClose();
    refreshDashboard();
  };

  const handleSubmitBranch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!branchForm.name) return;
    showNotification(t('dashboard.quick.branch_configured', { name: branchForm.name }));
    setBranchForm({ name: '', code: '', invoicePrefix: 'INV-' });
    handleClose();
    refreshDashboard();
  };

  const handleSubmitUser = (e: React.FormEvent) => {
    e.preventDefault();
    if (!userForm.name || !userForm.email) return;
    showNotification(t('dashboard.quick.user_added', { name: userForm.name, role: userForm.role }));
    setUserForm({ name: '', email: '', role: 'URY Cashier' });
    handleClose();
    refreshDashboard();
  };

  const actionCards = [
    {
      title: t('dashboard.quick.open_pos_title'),
      description: t('dashboard.quick.open_pos_desc'),
      actionText: t('dashboard.quick.open_pos_action'),
      color: 'bg-purple-600 hover:bg-purple-700 text-white',
      border: 'border-purple-200',
      icon: (
        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      ),
      onClick: () => navigate('/pos'),
    },
    {
      title: t('dashboard.quick.add_menu_title'),
      description: t('dashboard.quick.add_menu_desc'),
      actionText: t('dashboard.quick.add_menu_action'),
      color: 'bg-white hover:bg-purple-50 text-purple-700',
      border: 'border-gray-200 hover:border-purple-300',
      icon: (
        <svg className="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 6v6m0 0v6m0-6h6m-6 0H6"
          />
        </svg>
      ),
      onClick: () => setActiveModal('menu'),
    },
    {
      title: t('dashboard.quick.add_table_title'),
      description: t('dashboard.quick.add_table_desc'),
      actionText: t('dashboard.quick.add_table_action'),
      color: 'bg-white hover:bg-purple-50 text-purple-700',
      border: 'border-gray-200 hover:border-purple-300',
      icon: (
        <svg className="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
        </svg>
      ),
      onClick: () => setActiveModal('table'),
    },
    {
      title: t('dashboard.quick.add_room_title'),
      description: t('dashboard.quick.add_room_desc'),
      actionText: t('dashboard.quick.add_room_action'),
      color: 'bg-white hover:bg-purple-50 text-purple-700',
      border: 'border-gray-200 hover:border-purple-300',
      icon: (
        <svg className="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5m0 0v-5a2 2 0 012-2h2a2 2 0 012 2v5m-6 0h6"
          />
        </svg>
      ),
      onClick: () => setActiveModal('room'),
    },
    {
      title: t('dashboard.quick.add_branch_title'),
      description: t('dashboard.quick.add_branch_desc'),
      actionText: t('dashboard.quick.add_branch_action'),
      color: 'bg-white hover:bg-purple-50 text-purple-700',
      border: 'border-gray-200 hover:border-purple-300',
      icon: (
        <svg className="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5m0 0v-5a2 2 0 012-2h2a2 2 0 012 2v5m-6 0h6"
          />
        </svg>
      ),
      onClick: () => setActiveModal('branch'),
    },
    {
      title: t('dashboard.quick.add_user_title'),
      description: t('dashboard.quick.add_user_desc'),
      actionText: t('dashboard.quick.add_user_action'),
      color: 'bg-white hover:bg-purple-50 text-purple-700',
      border: 'border-gray-200 hover:border-purple-300',
      icon: (
        <svg className="h-6 w-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
          />
        </svg>
      ),
      onClick: () => setActiveModal('user'),
    },
  ];

  return (
    <section className="w-full">
      {/* Toast feedback banner */}
      {toastMessage && (
        <div className="mb-4 rounded-xl bg-purple-900 text-white px-4 py-3 shadow-md flex items-center justify-between text-xs font-semibold animate-fade-in">
          <span>{toastMessage}</span>
          <button onClick={() => setToastMessage(null)} className="text-purple-200 hover:text-white">
            {t('dashboard.quick.dismiss')}
          </button>
        </div>
      )}

      <div className="mb-3 flex items-center justify-between pb-3 border-b border-gray-200 -mx-6 px-6 -mt-6 pt-6">
        <h2 className="text-lg font-bold text-gray-900">{t('dashboard.quick.heading')}</h2>
        <span className="text-xs text-gray-500 font-medium">{t('dashboard.quick.shortcuts')}</span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {actionCards.map((card, idx) => (
          <Card
            key={idx}
            onClick={card.onClick}
            className={`cursor-pointer rounded-xl border ${card.border} p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md flex flex-col justify-between`}
          >
            <div>
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50">
                {card.icon}
              </div>
              <h3 className="font-bold text-sm text-gray-900">{card.title}</h3>
              <p className="mt-1 text-xs text-gray-500 line-clamp-2">{card.description}</p>
            </div>
            <div className="mt-4">
              <Button
                variant={idx === 0 ? 'default' : 'outline'}
                size="sm"
                className={`w-full justify-center text-xs font-bold ${idx === 0 ? 'bg-purple-600 hover:bg-purple-700 text-white' : 'border-purple-200 text-purple-700 hover:bg-purple-50'}`}
              >
                {card.actionText}
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {/* 1. Add Menu Drawer/Dialog */}
      <Dialog open={activeModal === 'menu'} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-white p-6 rounded-xl border border-gray-200 shadow-xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-gray-900">{t('dashboard.quick.menu_dialog_title')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmitMenu} className="space-y-4 mt-3 text-xs">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.item_name')}</label>
              <Input
                placeholder="Paneer Tikka Masala"
                value={menuForm.name}
                onChange={(e: any) => setMenuForm({ ...menuForm, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.course_category')}</label>
              <SearchableSelect
                id="course"
                value={menuForm.course}
                onChange={(_, value) => setMenuForm({ ...menuForm, course: value })}
                options={[
                  { value: 'Starters', label: t('dashboard.quick.course_starters') },
                  { value: 'Main Course', label: t('dashboard.quick.course_main') },
                  { value: 'Breads', label: t('dashboard.quick.course_breads') },
                  { value: 'Dessert', label: t('dashboard.quick.course_dessert') },
                  { value: 'Beverages', label: t('dashboard.quick.course_beverages') },
                ]}
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.price')}</label>
              <Input
                type="number"
                placeholder="280"
                value={menuForm.price}
                onChange={(e: any) => setMenuForm({ ...menuForm, price: e.target.value })}
                required
              />
            </div>
            <DialogFooter className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={handleClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="bg-purple-600 hover:bg-purple-700 text-white">
                {t('dashboard.quick.save_item')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 2. Add Table Drawer/Dialog */}
      <Dialog open={activeModal === 'table'} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-white p-6 rounded-xl border border-gray-200 shadow-xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-gray-900">{t('dashboard.quick.table_dialog_title')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmitTable} className="space-y-4 mt-3 text-xs">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.table_name')}</label>
              <Input
                placeholder="T-15"
                value={tableForm.name}
                onChange={(e: any) => setTableForm({ ...tableForm, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.seating_capacity')}</label>
              <Input
                type="number"
                placeholder="4"
                value={tableForm.seats}
                onChange={(e: any) => setTableForm({ ...tableForm, seats: e.target.value })}
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.dining_room')}</label>
              <SearchableSelect
                id="room"
                value={tableForm.room}
                onChange={(_, value) => setTableForm({ ...tableForm, room: value })}
                options={[
                  { value: 'Main Dining', label: t('dashboard.quick.room_main') },
                  { value: 'Terrace Garden', label: t('dashboard.quick.room_terrace') },
                  { value: 'AC Family Section', label: t('dashboard.quick.room_ac_family') },
                  { value: 'VIP Lounge', label: t('dashboard.quick.room_vip') },
                ]}
              />
            </div>
            <DialogFooter className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={handleClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="bg-purple-600 hover:bg-purple-700 text-white">
                {t('dashboard.quick.save_table')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 3. Add Room / Zone Dialog */}
      <Dialog open={activeModal === 'room'} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-white p-6 rounded-xl border border-gray-200 shadow-xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-gray-900">{t('dashboard.quick.zone_dialog_title')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmitRoom} className="space-y-4 mt-3 text-xs">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.zone_name')}</label>
              <Input
                placeholder="Outdoor Deck"
                value={roomForm.name}
                onChange={(e: any) => setRoomForm({ ...roomForm, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.zone_type')}</label>
              <SearchableSelect
                id="type"
                value={roomForm.type}
                onChange={(_, value) => setRoomForm({ ...roomForm, type: value })}
                options={[
                  { value: 'AC', label: t('dashboard.quick.zone_ac') },
                  { value: 'Non-AC', label: t('dashboard.quick.zone_non_ac') },
                  { value: 'Rooftop', label: t('dashboard.quick.zone_rooftop') },
                  { value: 'Bar', label: t('dashboard.quick.zone_bar') },
                ]}
              />
            </div>
            <DialogFooter className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={handleClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="bg-purple-600 hover:bg-purple-700 text-white">
                {t('dashboard.quick.save_zone')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 4. Add Branch Dialog */}
      <Dialog open={activeModal === 'branch'} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-white p-6 rounded-xl border border-gray-200 shadow-xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-gray-900">{t('dashboard.quick.branch_dialog_title')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmitBranch} className="space-y-4 mt-3 text-xs">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.branch_name')}</label>
              <Input
                placeholder="Waterfront Bistro"
                value={branchForm.name}
                onChange={(e: any) => setBranchForm({ ...branchForm, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.branch_code')}</label>
              <Input
                placeholder="WF-05"
                value={branchForm.code}
                onChange={(e: any) => setBranchForm({ ...branchForm, code: e.target.value })}
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.invoice_prefix')}</label>
              <Input
                placeholder="INV-WF-"
                value={branchForm.invoicePrefix}
                onChange={(e: any) => setBranchForm({ ...branchForm, invoicePrefix: e.target.value })}
              />
            </div>
            <DialogFooter className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={handleClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="bg-purple-600 hover:bg-purple-700 text-white">
                {t('dashboard.quick.create_branch')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 5. Add User Dialog */}
      <Dialog open={activeModal === 'user'} onOpenChange={handleClose}>
        <DialogContent className="max-w-md bg-white p-6 rounded-xl border border-gray-200 shadow-xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold text-gray-900">{t('dashboard.quick.user_dialog_title')}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmitUser} className="space-y-4 mt-3 text-xs">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.full_name')}</label>
              <Input
                placeholder="Karan Verma"
                value={userForm.name}
                onChange={(e: any) => setUserForm({ ...userForm, name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.email')}</label>
              <Input
                type="email"
                placeholder="karan@uryrestaurant.com"
                value={userForm.email}
                onChange={(e: any) => setUserForm({ ...userForm, email: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1">{t('dashboard.quick.role_permissions')}</label>
              <SearchableSelect
                id="role"
                value={userForm.role}
                onChange={(_, value) => setUserForm({ ...userForm, role: value })}
                options={[
                  { value: 'URY Cashier', label: t('dashboard.quick.role_cashier') },
                  { value: 'URY Captain', label: t('dashboard.quick.role_captain') },
                  { value: 'URY Manager', label: t('dashboard.quick.role_manager') },
                  { value: 'URY Kitchen User', label: t('dashboard.quick.role_kitchen') },
                ]}
              />
            </div>
            <DialogFooter className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={handleClose}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" className="bg-purple-600 hover:bg-purple-700 text-white">
                {t('dashboard.quick.create_user')}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
};

export default QuickActions;
