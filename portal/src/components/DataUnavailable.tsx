interface DataUnavailableProps {
  /** What is missing, e.g. "Audit journal". */
  feature: string;
  /** Frozen-dataset collection name, when the gap comes from the demo data. */
  datasetKey?: string;
}

/**
 * Shown when the data source has nothing to give: offline mode without the
 * collection in the frozen dataset, or an API that does not report the field.
 * Never an empty table, never invented rows.
 */
export function DataUnavailable({ feature, datasetKey }: DataUnavailableProps) {
  return (
    <div className="table-empty" data-testid="data-unavailable" role="status">
      {feature} — not available{datasetKey ? ` in the frozen dataset (demo/seed/demo-dataset.json has no \`${datasetKey}\` collection yet)` : ' from the API'}.
    </div>
  );
}
