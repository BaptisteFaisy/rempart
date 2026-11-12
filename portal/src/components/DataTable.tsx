import { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  /** Field used as the React key; prefer `rowKey` for rows without a scalar id. */
  keyField?: keyof T;
  rowKey?: (row: T, index: number) => string;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
}

export function DataTable<T>({
  columns,
  data,
  keyField,
  rowKey,
  emptyMessage = 'No records found',
  onRowClick
}: DataTableProps<T>) {
  if (data.length === 0) {
    return (
      <div className="table-empty" data-testid="table-empty">
        {emptyMessage}
      </div>
    );
  }

  const keyOf = (row: T, index: number): string =>
    rowKey ? rowKey(row, index) : String(keyField ? row[keyField] : index);

  return (
    <div className="table-container">
      <table className="data-table" data-testid="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr
              key={keyOf(row, index)}
              onClick={() => onRowClick?.(row)}
              className={onRowClick ? 'clickable-row' : ''}
            >
              {columns.map((c) => (
                <td key={c.key}>
                  {c.render
                    ? c.render(row)
                    : String(row[c.key as keyof T] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
