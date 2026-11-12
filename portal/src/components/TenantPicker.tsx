import { Tenant } from '../types';

interface TenantPickerProps {
  tenants: Tenant[];
  value: string;
  onChange: (tenantId: string) => void;
  allowAll?: boolean;
  label?: string;
}

/** Tenant selector shared by the tenant-scoped pages. */
export function TenantPicker({
  tenants,
  value,
  onChange,
  allowAll = false,
  label = 'Client'
}: TenantPickerProps) {
  return (
    <div className="form-group" style={{ maxWidth: 320, marginBottom: 16 }}>
      <label htmlFor="tenant-picker">{label}</label>
      <select
        id="tenant-picker"
        className="form-control"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid="tenant-picker"
      >
        {allowAll ? <option value="">All tenants</option> : null}
        {tenants.map((t) => (
          <option key={t.tenant_id} value={t.tenant_id}>
            {t.name} ({t.tenant_id})
          </option>
        ))}
      </select>
    </div>
  );
}
