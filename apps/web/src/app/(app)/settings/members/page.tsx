"use client";

import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth-context";
import {
  Alert,
  Badge,
  Button,
  Card,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Invitation, Member, Role } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const ROLES: Role[] = ["owner", "admin", "reviewer", "viewer"];
const ROLE_HELP: Record<Role, string> = {
  owner: "Full control, including managing admins and owners.",
  admin:
    "Settings, members (reviewers/viewers), bank verification, final approval, overrides, audit log.",
  reviewer: "Upload and correct invoices, first-step review, vendors and POs.",
  viewer: "Read-only access to invoices, vendors, POs and dashboards.",
};

export default function MembersPage() {
  const { me, can } = useAuth();
  const members = useApi<Member[]>("/organization/members");
  const invitations = useApi<Invitation[]>(
    can("members.manage") ? "/organization/invitations" : null,
  );
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("reviewer");
  const [created, setCreated] = useState<Invitation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const manage = can("members.manage");
  const assignable = me.organization?.role === "owner" ? ROLES : (["reviewer", "viewer"] as Role[]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setCreated(await api<Invitation>("/organization/invitations", { json: { email, role } }));
      setEmail("");
      invitations.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  const update = async (member: Member, change: { role?: Role; status?: string }) => {
    setError(null);
    try {
      await api(`/organization/members/${member.membership_id}`, { method: "PATCH", json: change });
      members.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <>
      <PageHeader
        title="Members and roles"
        description="Permissions are enforced by the server for every request."
      />
      {error ? (
        <div className="mb-4">
          <Alert tone="danger">{error}</Alert>
        </div>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div>
          {members.loading ? (
            <Loading />
          ) : (
            <Table caption="Members">
              <thead>
                <tr>
                  <Th>Member</Th>
                  <Th>Role</Th>
                  <Th>Status</Th>
                  <Th>Joined</Th>
                </tr>
              </thead>
              <tbody>
                {(members.data ?? []).map((m) => {
                  const self = m.user_id === me.user_id;
                  const canEdit = manage && !self && assignable.includes(m.role);
                  return (
                    <tr key={m.membership_id}>
                      <Td>
                        {m.full_name}
                        <div className="text-xs text-muted">
                          {m.email}
                          {self ? " (you)" : ""}
                        </div>
                      </Td>
                      <Td>
                        {canEdit ? (
                          <Select
                            aria-label={`Role for ${m.email}`}
                            value={m.role}
                            onChange={(e) => void update(m, { role: e.target.value as Role })}
                            className="w-auto"
                          >
                            {assignable.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </Select>
                        ) : (
                          <span className="capitalize">{m.role}</span>
                        )}
                      </Td>
                      <Td>
                        <Badge tone={m.status === "active" ? "success" : "neutral"}>
                          {m.status}
                        </Badge>
                        {canEdit ? (
                          <button
                            type="button"
                            className="ml-2 text-xs text-accent hover:underline"
                            onClick={() =>
                              void update(m, {
                                status: m.status === "active" ? "disabled" : "active",
                              })
                            }
                          >
                            {m.status === "active" ? "Disable" : "Enable"}
                          </button>
                        ) : null}
                      </Td>
                      <Td className="text-muted">{formatDate(m.joined_at)}</Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          <Card title="Role permissions" className="mt-6">
            <dl className="space-y-2 text-sm">
              {ROLES.map((r) => (
                <div key={r}>
                  <dt className="font-medium capitalize">{r}</dt>
                  <dd className="text-muted">{ROLE_HELP[r]}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>
        {manage ? (
          <Card title="Invite a member">
            <form onSubmit={invite} className="space-y-3">
              <Field label="Email">
                {(p) => (
                  <Input
                    id={p.id}
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                )}
              </Field>
              <Field label="Role">
                {(p) => (
                  <Select id={p.id} value={role} onChange={(e) => setRole(e.target.value as Role)}>
                    {assignable.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <Button type="submit">Create invitation</Button>
            </form>
            {created?.invitation_url ? (
              <Alert tone="info" title="Share this link with the invitee">
                <code className="break-all text-xs">{created.invitation_url}</code>
                <p className="mt-1 text-xs text-muted">
                  Valid until {formatDate(created.expires_at)}. Email delivery is not enabled in
                  this version.
                </p>
              </Alert>
            ) : null}
            {(invitations.data ?? []).length > 0 ? (
              <ul className="mt-4 space-y-1 text-sm">
                <li className="font-medium">Pending invitations</li>
                {(invitations.data ?? []).map((i) => (
                  <li key={i.id} className="text-muted">
                    {i.email} · {i.role}
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>
        ) : null}
      </div>
    </>
  );
}
