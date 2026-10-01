import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { http } from "../api/client";
import { Plus, Trash2, Shield, UserCircle, CheckCircle2, XCircle } from "lucide-react";

export default function AdminUsers() {
  const queryClient = useQueryClient();
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState("USER");
  const [newPassword, setNewPassword] = useState("");

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => http.get("/auth/users").then(r => r.data)
  });

  const addUser = useMutation({
    mutationFn: (data) => http.post("/auth/users", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      setNewEmail("");
      setNewPassword("");
    }
  });

  const toggleStatus = useMutation({
    mutationFn: ({ id, is_active }) => http.put(`/auth/users/${id}`, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] })
  });

  const removeUser = useMutation({
    mutationFn: (id) => http.delete(`/auth/users/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-users"] })
  });

  if (isLoading) return <div className="p-6 text-text-muted">Loading users...</div>;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-bold text-text-primary">User Access</h2>
          <p className="text-sm text-text-secondary mt-1">Manage who can access RETAILYNX via email &amp; password.</p>
        </div>
      </div>

      <div className="bg-card border border-border rounded-xl shadow-sm p-5">
        <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">Add User</h3>
        <form
          className="flex items-end gap-4 flex-wrap"
          onSubmit={(e) => {
            e.preventDefault();
            if (newEmail.trim())
              addUser.mutate({
                email: newEmail.trim(),
                role: newRole,
                password: newPassword || undefined,
              });
          }}
        >
          <div className="flex-1 min-w-[220px] space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Email</label>
            <input
              type="email"
              required
              value={newEmail}
              onChange={e => setNewEmail(e.target.value)}
              placeholder="user@company.com"
              className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
          <div className="flex-1 min-w-[200px] space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Password</label>
            <input
              type="text"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder="Initial password (optional)"
              className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
          <div className="w-48 space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Role</label>
            <select
              value={newRole}
              onChange={e => setNewRole(e.target.value)}
              className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            >
              <option value="USER">USER</option>
              <option value="ADMIN">ADMIN</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={addUser.isPending}
            className="bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center gap-2 h-[38px] disabled:opacity-50"
          >
            <Plus size={16} /> Add User
          </button>
        </form>
      </div>

      <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-base/50 border-b border-border">
            <tr>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs">Email</th>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs">Role</th>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs">Status</th>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-card-hover/50 transition-colors">
                <td className="px-5 py-3 font-medium text-text-primary">{u.email}</td>
                <td className="px-5 py-3">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-bold tracking-wide ${
                    u.role === 'ADMIN' ? 'bg-accent-soft text-accent' : 'bg-surface border border-border text-text-secondary'
                  }`}>
                    {u.role === 'ADMIN' ? <Shield size={12} /> : <UserCircle size={12} />}
                    {u.role}
                  </span>
                </td>
                <td className="px-5 py-3">
                  <button
                    onClick={() => toggleStatus.mutate({ id: u.id, is_active: !u.is_active })}
                    className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-colors ${
                      u.is_active
                        ? 'text-positive hover:bg-positive-soft'
                        : 'text-text-muted hover:bg-surface'
                    }`}
                  >
                    {u.is_active ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                    {u.is_active ? 'Active' : 'Disabled'}
                  </button>
                </td>
                <td className="px-5 py-3 text-right">
                  <button
                    onClick={() => {
                      if (window.confirm(`Remove ${u.email}?`)) removeUser.mutate(u.id);
                    }}
                    className="p-1.5 text-text-muted hover:text-negative hover:bg-negative-soft rounded transition-colors"
                    title="Remove User"
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-8 text-center text-text-muted">
                  No users found. Add one above.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
