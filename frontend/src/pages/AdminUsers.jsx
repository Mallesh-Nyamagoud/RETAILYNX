import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { http } from "../api/client";
import { Plus, Trash2, CheckCircle2, XCircle, KeyRound } from "lucide-react";

const MIN_PASSWORD_LENGTH = 8;

export default function AdminUsers() {
  const queryClient = useQueryClient();
  const [newUsername, setNewUsername] = useState("");
  const [newRole, setNewRole] = useState("USER");
  const [newPassword, setNewPassword] = useState("");
  const [notice, setNotice] = useState(null);
  // Which row currently has its "reset password" input open, and the value.
  const [resetFor, setResetFor] = useState(null);
  const [resetPassword, setResetPassword] = useState("");

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => http.get("/auth/users").then(r => r.data)
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin-users"] });
  const onError = (err) => setNotice({ kind: "error", text: err?.message || "Something went wrong." });

  const addUser = useMutation({
    mutationFn: (data) => http.post("/auth/users", data),
    onSuccess: (res) => {
      refresh();
      setNewUsername("");
      setNewPassword("");
      setNotice({ kind: "ok", text: `User '${res.data.username}' created.` });
    },
    onError,
  });

  // One endpoint handles set-password, change-role and enable/disable.
  const updateUser = useMutation({
    mutationFn: ({ id, ...changes }) => http.put(`/auth/users/${id}`, changes),
    onSuccess: () => {
      refresh();
      setResetFor(null);
      setResetPassword("");
      setNotice({ kind: "ok", text: "User updated." });
    },
    onError,
  });

  const removeUser = useMutation({
    mutationFn: (id) => http.delete(`/auth/users/${id}`),
    onSuccess: () => {
      refresh();
      setNotice({ kind: "ok", text: "User removed." });
    },
    onError,
  });

  if (isLoading) return <div className="p-6 text-text-muted">Loading users...</div>;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-display font-bold text-text-primary">User Access</h2>
          <p className="text-sm text-text-secondary mt-1">Manage who can access RETAILYNX with a username &amp; password.</p>
        </div>
      </div>

      {notice && (
        <div className={`text-sm rounded-lg px-4 py-2.5 border ${
          notice.kind === "ok"
            ? "text-positive bg-positive-soft border-positive/30"
            : "text-negative bg-negative-soft border-negative/30"
        }`}>
          {notice.text}
        </div>
      )}

      <div className="bg-card border border-border rounded-xl shadow-sm p-5">
        <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4">Add User</h3>
        <form
          className="flex items-end gap-4 flex-wrap"
          onSubmit={(e) => {
            e.preventDefault();
            setNotice(null);
            if (!newUsername.trim()) return;
            if (newPassword && newPassword.length < MIN_PASSWORD_LENGTH) {
              setNotice({ kind: "error", text: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.` });
              return;
            }
            addUser.mutate({
              username: newUsername.trim(),
              role: newRole,
              password: newPassword || undefined,
            });
          }}
        >
          <div className="flex-1 min-w-[220px] space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Username</label>
            <input
              type="text"
              required
              value={newUsername}
              onChange={e => setNewUsername(e.target.value)}
              placeholder="e.g. analyst1"
              className="w-full bg-base border border-border rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
          <div className="flex-1 min-w-[200px] space-y-1.5">
            <label className="text-xs font-medium text-text-muted">Password</label>
            <input
              type="text"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              placeholder={`Initial password (min ${MIN_PASSWORD_LENGTH} chars)`}
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
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs">Username</th>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs">Role</th>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs">Status</th>
              <th className="px-5 py-3 font-semibold text-text-muted uppercase tracking-wider text-xs text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {users.map(u => (
              <tr key={u.id} className="hover:bg-card-hover/50 transition-colors align-top">
                <td className="px-5 py-3 font-medium text-text-primary">{u.username}</td>
                <td className="px-5 py-3">
                  <select
                    value={u.role}
                    disabled={updateUser.isPending}
                    onChange={(e) => {
                      if (e.target.value === u.role) return;
                      setNotice(null);
                      updateUser.mutate({ id: u.id, role: e.target.value });
                    }}
                    title="Change role"
                    className={`bg-base border border-border rounded-md px-2 py-1 text-[11px] font-bold tracking-wide focus:outline-none focus:border-accent ${
                      u.role === 'ADMIN' ? 'text-accent' : 'text-text-secondary'
                    }`}
                  >
                    <option value="USER">USER</option>
                    <option value="ADMIN">ADMIN</option>
                  </select>
                </td>
                <td className="px-5 py-3">
                  <button
                    onClick={() => {
                      setNotice(null);
                      updateUser.mutate({ id: u.id, is_active: !u.is_active });
                    }}
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
                <td className="px-5 py-3">
                  <div className="flex items-start justify-end gap-1">
                    {resetFor === u.id ? (
                      <form
                        className="flex items-center gap-1.5"
                        onSubmit={(e) => {
                          e.preventDefault();
                          setNotice(null);
                          if (resetPassword.length < MIN_PASSWORD_LENGTH) {
                            setNotice({
                              kind: "error",
                              text: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
                            });
                            return;
                          }
                          updateUser.mutate({ id: u.id, password: resetPassword });
                        }}
                      >
                        <input
                          type="text"
                          autoFocus
                          value={resetPassword}
                          onChange={(e) => setResetPassword(e.target.value)}
                          placeholder={`New password (min ${MIN_PASSWORD_LENGTH})`}
                          className="w-52 bg-base border border-border rounded-md px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent"
                        />
                        <button
                          type="submit"
                          disabled={updateUser.isPending}
                          className="px-2 py-1 rounded-md text-xs font-semibold text-white bg-accent hover:bg-accent-hover disabled:opacity-50"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => { setResetFor(null); setResetPassword(""); }}
                          className="px-2 py-1 rounded-md text-xs font-medium text-text-muted hover:bg-surface"
                        >
                          Cancel
                        </button>
                      </form>
                    ) : (
                      <>
                        <button
                          onClick={() => { setNotice(null); setResetFor(u.id); setResetPassword(""); }}
                          className="p-1.5 text-text-muted hover:text-accent hover:bg-accent-soft rounded transition-colors"
                          title="Set / reset password"
                        >
                          <KeyRound size={16} />
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm(`Remove ${u.username}?`)) {
                              setNotice(null);
                              removeUser.mutate(u.id);
                            }
                          }}
                          className="p-1.5 text-text-muted hover:text-negative hover:bg-negative-soft rounded transition-colors"
                          title="Remove User"
                        >
                          <Trash2 size={16} />
                        </button>
                      </>
                    )}
                  </div>
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
