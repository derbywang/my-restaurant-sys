import React, { useState, useEffect } from 'react';
import { useBranchContext } from '../../context/BranchContext';
import { Users, Plus, ShieldCheck, Edit2 } from 'lucide-react';
import { Card, Button, Badge, Input, Spinner, showToast, Dialog, DialogContent, DialogHeader, DialogTitle } from '@ury/ui';
import { t } from '../../i18n';
import { STAFF_ROLES, serverErrorKeyOf, validateStaffAccount } from '../../utils/staffAccount';
import { SearchableSelect } from '../../components/common/SearchableSelect';
import { Switch } from '../../components/ui/switch';
import { dashboardService } from '../../services/dashboard';
import { call } from '@ury/core';
import SideDrawer from '../../components/layout/SideDrawer';
import { modulePermissionsFrom } from '../../utils/permission';

interface UserRecord {
  name: string;
  email: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
  user_type?: string;
  enabled?: number;
  roles?: Array<{ role: string }>;
}

export const UserPage: React.FC = () => {
  const { activeBranchId } = useBranchContext();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);
  const [saving, setSaving] = useState<boolean>(false);
  // what the server allows this user to do with User records; hidden until the answer is a yes
  const [canCreateUser, setCanCreateUser] = useState<boolean>(false);
  const [canEditUser, setCanEditUser] = useState<boolean>(false);

  // the manager makes the accounts of the staff through one narrow call (ury/ury/api/staff_accounts.py); the password is shown once
  const [staffOptionsFailed, setStaffOptionsFailed] = useState<boolean>(false);
  const [staffOptions, setStaffOptions] = useState<{ can_create: boolean; roles: string[]; branches: string[] }>({ can_create: false, roles: [], branches: [] });
  const [staffDrawer, setStaffDrawer] = useState(false);
  const [staffForm, setStaffForm] = useState({ first_name: '', last_name: '', login_id: '', role: 'URY Cashier', branch: '' });
  const [staffSaving, setStaffSaving] = useState(false);
  const [staffResult, setStaffResult] = useState<{ login_id: string; full_name: string; role: string; branch: string; initial_password: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const staffRoleLabel = (role: string) => {
    const known = STAFF_ROLES.find((r) => r.role === role);
    return known ? t(`staff_account.role_${known.key}`) : role;
  };

  const [newUser, setNewUser] = useState({
    first_name: '',
    last_name: '',
    email: '',
    role: 'URY Cashier',
    enabled: true,
  });
  const [originalUser, setOriginalUser] = useState<any>(null);
  const [allRoles, setAllRoles] = useState<{name: string}[]>([]);

  const fetchRoles = async () => {
    try {
      const res = await call<any>('frappe.client.get_list', { doctype: 'Role', fields: ['name'], limit: 1000 });
      const records = res.message || res;
      setAllRoles(Array.isArray(records) ? records : []);
    } catch (err) {
      console.error('Failed to fetch roles', err);
      setAllRoles([]);
    }
  };

  const URY_ROLES = ['URY Manager', 'URY Waiter', 'URY Cashier'];

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const records = await dashboardService.getModuleRecords<UserRecord>('User', activeBranchId);
      setUsers(records);
    } catch {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
    fetchRoles();
  }, [activeBranchId]);

  useEffect(() => {
    const ask = async () => {
      try {
        const answer = modulePermissionsFrom(await call('ury.ury.api.dashboard.get_module_permissions', { doctype: 'User' }));
        setCanCreateUser(answer.create);
        setCanEditUser(answer.write);
      } catch {
        setCanCreateUser(false);
        setCanEditUser(false);
      }
    };
    ask();
  }, []);

  useEffect(() => {
    call.get('ury.ury.api.staff_accounts.get_staff_account_options')
      .then((res: any) => setStaffOptions((res.message ?? res) as typeof staffOptions))
      .catch(() => {
        setStaffOptions({ can_create: false, roles: [], branches: [] });
        setStaffOptionsFailed(true);
      });
  }, []);

  const openStaffDrawer = () => {
    setStaffForm({ first_name: '', last_name: '', login_id: '', role: staffOptions.roles[0] ?? 'URY Cashier', branch: staffOptions.branches.length === 1 ? staffOptions.branches[0] : '' });
    setStaffDrawer(true);
  };

  const handleCreateStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    const problem = validateStaffAccount(staffForm, staffOptions.roles);
    if (problem) {
      showToast.error(t(`staff_account.${problem}`));
      return;
    }
    setStaffSaving(true);
    try {
      const res: any = await call.post('ury.ury.api.staff_accounts.create_staff_account', {
        first_name: staffForm.first_name.trim(),
        last_name: staffForm.last_name.trim() || undefined,
        login_id: staffForm.login_id.trim(),
        role: staffForm.role,
        branch: staffForm.branch || undefined,
      });
      setStaffDrawer(false);
      setCopied(false);
      setStaffResult(res.message ?? res);
      fetchUsers();
    } catch (err) {
      showToast.error(t(`staff_account.${serverErrorKeyOf(err) || 'failed'}`));
    } finally {
      setStaffSaving(false);
    }
  };

  // the password is kept only while the window is open: closing it forgets it
  const closeStaffResult = () => {
    setStaffResult(null);
    setCopied(false);
  };

  const copyPassword = async () => {
    if (!staffResult) return;
    try {
      await navigator.clipboard.writeText(staffResult.initial_password);
      setCopied(true);
    } catch {
      // the browser may refuse (not a secure page): the password is on the screen to be written down
    }
  };

  const getDisplayRole = (user: UserRecord): string => {
    if (user.roles && Array.isArray(user.roles) && user.roles.length > 0) {
      return user.roles[0].role;
    }
    return 'User';
  };

  const openAddDrawer = () => {
    setEditingUser(null);
    setNewUser({ first_name: '', last_name: '', email: '', role: 'URY Cashier', enabled: true });
    setIsDrawerOpen(true);
  };

  const openEditDrawer = async (user: UserRecord) => {
    setEditingUser(user);
    let userRole = 'URY Cashier';

    try {
      const fullUserRes = await call('frappe.client.get', {
        doctype: 'User',
        name: user.name,
      });
      const fullUser = (fullUserRes as any).message || fullUserRes;

      if (fullUser.roles && Array.isArray(fullUser.roles) && fullUser.roles.length > 0) {
        userRole = fullUser.roles[0].role;
      }
    } catch (err) {
      console.error('Failed to fetch user roles', err);
    }
    
    if (userRole === 'URY Cashier' && user.roles && Array.isArray(user.roles) && user.roles.length > 0) {
      userRole = user.roles[0].role;
    }

    const initialForm = {
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      email: user.email || '',
      role: userRole,
      enabled: user.enabled === 1,
    };
    setNewUser(initialForm);
    setOriginalUser(initialForm);
    setIsDrawerOpen(true);
  };

  const handleSaveUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUser.email) return;

    if (editingUser && originalUser) {
      const original = {
        first_name: (originalUser.first_name || '').trim(),
        last_name: (originalUser.last_name || '').trim(),
        role: originalUser.role,
        enabled: originalUser.enabled ? 1 : 0,
      };
      const current = {
        first_name: (newUser.first_name || '').trim(),
        last_name: (newUser.last_name || '').trim(),
        role: newUser.role,
        enabled: newUser.enabled ? 1 : 0,
      };
      if (JSON.stringify(original) === JSON.stringify(current)) {
        showToast.warning('No changes in document');
        return;
      }
    }

    setSaving(true);
    try {
      if (editingUser) {
        await call('frappe.client.set_value', {
          doctype: 'User',
          name: editingUser.name,
          fieldname: {
            first_name: newUser.first_name,
            last_name: newUser.last_name,
            enabled: newUser.enabled ? 1 : 0,
          },
        });

        if (newUser.role) {
          const fullUserRes = await call('frappe.client.get', {
            doctype: 'User',
            name: editingUser.name,
          });
          const fullUser = (fullUserRes as any).message || fullUserRes;

          let updatedRoles = fullUser.roles && Array.isArray(fullUser.roles) ? [...fullUser.roles] : [];
          updatedRoles = [{ role: newUser.role }];

          await call('frappe.client.set_value', {
            doctype: 'User',
            name: editingUser.name,
            fieldname: 'roles',
            value: updatedRoles,
          });
        }
      } else {
        await call('frappe.client.insert', {
          doc: {
            doctype: 'User',
            email: newUser.email,
            first_name: newUser.first_name,
            last_name: newUser.last_name,
            send_welcome_email: 1,
            enabled: newUser.enabled ? 1 : 0,
            roles: [{ role: newUser.role }],
          },
        });
      }
      fetchUsers();
      setIsDrawerOpen(false);
      showToast.success(`User ${editingUser ? 'updated' : 'added'} successfully`);
    } catch (err: any) {
      console.error('Failed to save User', err);
      let errorMessage = 'Failed to save User';
      if (err._server_messages) {
        try {
          const messages = JSON.parse(err._server_messages);
          if (messages.length > 0) {
            const lastMessage = JSON.parse(messages[messages.length - 1]);
            if (lastMessage.message) {
              errorMessage = lastMessage.message.replace(/<[^>]*>?/gm, '');
            }
          }
        } catch (e) {}
      } else if (err.message) {
        errorMessage = err.message;
      } else if (err.exc) {
        errorMessage = 'Duplicate entry or server error occurred.';
      }
      showToast.error(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Toolbar — no title, partition style. Adding users is for those who may create a User. */}
      {(canCreateUser || staffOptions.can_create) && (
        <div className="flex flex-col md:flex-row items-center justify-end gap-4 pb-3 border-b border-gray-200 -mx-6 px-6 -mt-6 pt-6">
          {!canCreateUser && staffOptions.can_create && <p className="flex-1 text-xs text-gray-500">{t('staff_account.hint')}</p>}
          <Button
            onClick={canCreateUser ? openAddDrawer : openStaffDrawer}
            className="bg-primary hover:bg-primary/90 text-white font-semibold flex items-center space-x-1.5 shadow-xs"
          >
            <Plus className="w-4 h-4" />
            <span>{canCreateUser ? 'Add User' : t('staff_account.add')}</span>
          </Button>
        </div>
      )}

      {staffOptionsFailed && (
        <p className="text-xs text-red-600" role="alert" data-testid="staff-options-failed">{t('staff_account.options_failed')}</p>
      )}

      {loading ? (
        <div className="py-16 flex items-center justify-center bg-white rounded-lg border border-gray-200">
          <Spinner className="w-8 h-8 text-primary" />
        </div>
      ) : users.length === 0 ? (
        <Card className="p-12 flex flex-col items-center justify-center text-center rounded-lg border border-gray-200 shadow-sm bg-white">
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mb-4">
            <Users className="w-6 h-6 text-primary" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900 mb-1">No Users Configured</h3>
          <p className="text-gray-500 mb-6 max-w-sm">
            {canCreateUser ? 'Add staff users and assign them roles for this branch.' : 'There are no users to show.'}
          </p>
          {canCreateUser && (
            <Button
              onClick={openAddDrawer}
              className="bg-primary hover:bg-primary/90 text-white font-semibold flex items-center space-x-1.5 shadow-xs"
            >
              <Plus className="w-4 h-4" />
              <span>Add User</span>
            </Button>
          )}
        </Card>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
          <table className="w-full text-left text-sm text-gray-600">
            <thead className="bg-gray-50 border-b border-gray-100 text-xs uppercase text-gray-500 font-semibold">
              <tr>
                <th className="px-6 py-4">User</th>
                <th className="px-6 py-4">User ID</th>
                <th className="px-6 py-4">Role</th>
                {canEditUser && <th className="px-6 py-4 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((user) => (
                <tr key={user.name} className="hover:bg-primary/10 transition-colors">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-xs uppercase shrink-0">
                        {(user.first_name || user.email || user.name || '?').charAt(0)}
                      </div>
                      <div className="font-semibold text-gray-900">
                        {user.first_name || user.full_name || user.name}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-gray-600 font-medium">
                    {user.email}
                  </td>
                  <td className="px-6 py-4">
                    <Badge variant="outline" className="border-primary/20 bg-primary/10 text-primary text-[10px]">
                      <ShieldCheck className="w-3 h-3 mr-1" />
                      {getDisplayRole(user)}
                    </Badge>
                  </td>
                  {canEditUser && (
                  <td className="px-6 py-4 text-right">
                      <Button variant="ghost" size="sm" onClick={() => openEditDrawer(user)} className="text-gray-500 hover:text-primary">
                        <Edit2 className="w-4 h-4" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* The manager makes the account of a member of staff */}
      <SideDrawer isOpen={staffDrawer} onClose={() => setStaffDrawer(false)} title={t('staff_account.title')}>
        <form onSubmit={handleCreateStaff} className="space-y-5 text-sm" data-testid="staff-account-form">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-gray-700 mb-1.5">{t('staff_account.first_name')}</label>
              <Input value={staffForm.first_name} onChange={(e) => setStaffForm({ ...staffForm, first_name: e.target.value })} required />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1.5">{t('staff_account.last_name')}</label>
              <Input value={staffForm.last_name} onChange={(e) => setStaffForm({ ...staffForm, last_name: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="block font-semibold text-gray-700 mb-1.5">{t('staff_account.login_id')}</label>
            <Input type="email" value={staffForm.login_id} onChange={(e) => setStaffForm({ ...staffForm, login_id: e.target.value })} required />
          </div>
          <div>
            <label className="block font-semibold text-gray-700 mb-1.5">{t('staff_account.role')}</label>
            <SearchableSelect
              id="staff-role"
              value={staffForm.role}
              onChange={(_, value) => setStaffForm({ ...staffForm, role: value })}
              options={staffOptions.roles.map((role) => ({ value: role, label: staffRoleLabel(role) }))}
            />
          </div>
          {staffOptions.branches.length > 1 && (
            <div>
              <label className="block font-semibold text-gray-700 mb-1.5">{t('layout.header.branch') !== 'layout.header.branch' ? t('layout.header.branch') : 'Branch'}</label>
              <SearchableSelect
                id="staff-branch"
                value={staffForm.branch}
                onChange={(_, value) => setStaffForm({ ...staffForm, branch: value })}
                options={staffOptions.branches.map((b) => ({ value: b, label: b }))}
              />
            </div>
          )}
          <div className="pt-6 flex justify-end gap-3 border-t mt-4 border-gray-100">
            <Button type="button" variant="outline" onClick={() => setStaffDrawer(false)} disabled={staffSaving}>
              {t('staff_account.cancel')}
            </Button>
            <Button type="submit" className="bg-primary hover:bg-primary/90 text-white px-6" disabled={staffSaving}>
              {t('staff_account.submit')}
            </Button>
          </div>
        </form>
      </SideDrawer>

      {/* The password: shown once, kept only while this window is open */}
      <Dialog open={staffResult !== null} onOpenChange={(open) => { if (!open) closeStaffResult(); }}>
        <DialogContent className="max-w-md" data-testid="staff-account-result">
          <DialogHeader>
            <DialogTitle>{t('staff_account.result_title')}</DialogTitle>
          </DialogHeader>
          {staffResult && (
            <div className="space-y-4 text-sm">
              <p className="text-gray-700">
                {staffResult.full_name}（{staffRoleLabel(staffResult.role)} / {staffResult.branch}）
              </p>
              <div>
                <div className="text-xs text-gray-500">{t('staff_account.login_id')}</div>
                <div className="font-mono text-base" data-testid="staff-login-id">{staffResult.login_id}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500">{t('staff_account.result_password')}</div>
                <div className="flex items-center gap-3">
                  <div className="font-mono text-2xl tracking-wider select-all" data-testid="staff-initial-password">{staffResult.initial_password}</div>
                  <Button type="button" variant="outline" size="sm" onClick={copyPassword}>{copied ? t('staff_account.copied') : t('staff_account.copy')}</Button>
                </div>
              </div>
              <p className="rounded bg-red-50 border border-red-200 p-3 font-semibold text-red-800">{t('staff_account.password_once')}</p>
              <p className="text-gray-600">{t('staff_account.password_change')}</p>
              <div className="flex justify-end">
                <Button type="button" className="bg-primary hover:bg-primary/90 text-white px-6" onClick={closeStaffResult}>{t('staff_account.close')}</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Add/Edit SideDrawer */}
      <SideDrawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        title={editingUser ? 'Edit User' : 'Add User'}
      >
        <form onSubmit={handleSaveUser} className="space-y-5 text-sm">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-gray-700 mb-1.5">First Name</label>
              <Input
                value={newUser.first_name}
                onChange={(e) => setNewUser({ ...newUser, first_name: e.target.value })}
                required
              />
            </div>
            <div>
              <label className="block font-semibold text-gray-700 mb-1.5">Last Name</label>
              <Input
                value={newUser.last_name}
                onChange={(e) => setNewUser({ ...newUser, last_name: e.target.value })}
              />
            </div>
          </div>

          <div>
            <label className="block font-semibold text-gray-700 mb-1.5">User ID</label>
            <Input
              type="email"
              value={newUser.email}
              onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
              required
              disabled={!!editingUser}
            />
          </div>

          <div>
            <label className="block font-semibold text-gray-700 mb-1.5">Role</label>
            <SearchableSelect
              id="role"
              value={newUser.role}
              onChange={(_, value) => setNewUser({ ...newUser, role: value })}
              options={
                allRoles.length > 0 
                  ? allRoles.map(r => ({ value: r.name, label: r.name }))
                  : [
                      { value: 'URY Cashier', label: 'URY Cashier' },
                      { value: 'URY Waiter', label: 'URY Waiter' },
                      { value: 'URY Manager', label: 'URY Manager' },
                    ]
              }
            />
          </div>

          <div className="pt-6 flex justify-end gap-3 border-t mt-4 border-gray-100">
            <Button type="button" variant="outline" onClick={() => setIsDrawerOpen(false)} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" className="bg-primary hover:bg-primary/90 text-white px-6 flex items-center gap-2" disabled={saving}>
              {editingUser ? 'Save Changes' : 'Create User'}
            </Button>
          </div>
        </form>
      </SideDrawer>
    </div>
  );
};

export default UserPage;
