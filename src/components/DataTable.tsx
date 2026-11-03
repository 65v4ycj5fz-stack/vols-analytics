import {
  flexRender, getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable,
  type ColumnDef, type SortingState,
} from "@tanstack/react-table";
import { useId, useState } from "react";

/** Sortable, filterable table. Columns can be hidden on small screens with meta.hideSm. */
export function DataTable<T>({ data, columns, initialSort = [], filterPlaceholder, caption, maxHeight = "32rem",
  rowClassName }: {
  data: T[]; columns: ColumnDef<T, unknown>[]; initialSort?: SortingState; filterPlaceholder?: string;
  caption?: string; maxHeight?: string; rowClassName?: (row: T) => string;
}) {
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const [filter, setFilter] = useState("");
  const id = useId();
  const table = useReactTable({
    data, columns, state: { sorting, globalFilter: filter },
    onSortingChange: setSorting, onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(), sortDescFirst: true,
  });
  return (
    <div>
      {filterPlaceholder && (
        <div className="mb-2">
          <label htmlFor={id} className="sr-only">{filterPlaceholder}</label>
          <input id={id} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={filterPlaceholder}
            className="w-full max-w-xs rounded-md border border-line bg-surface px-2 py-1.5 text-sm" />
        </div>
      )}
      <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }} tabIndex={0} role="region" aria-label={caption ?? "Data table"}>
        <table className="w-full border-collapse text-sm">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead className="sticky top-0 z-10 bg-surface-2">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sorted = h.column.getIsSorted();
                  const meta = h.column.columnDef.meta as { hideSm?: boolean; align?: string } | undefined;
                  return (
                    <th key={h.id} scope="col"
                      aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : "none"}
                      className={`whitespace-nowrap border-b border-line px-2 py-2 text-xs font-semibold text-ink-2 ${meta?.align === "left" ? "text-left" : "text-right"} ${meta?.hideSm ? "hidden sm:table-cell" : ""}`}>
                      {h.isPlaceholder ? null : h.column.getCanSort() ? (
                        <button type="button" onClick={h.column.getToggleSortingHandler()} className="inline-flex items-center gap-1 hover:text-ink">
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          <span aria-hidden className="text-ink-3">{sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : "↕"}</span>
                        </button>
                      ) : flexRender(h.column.columnDef.header, h.getContext())}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((r) => (
              <tr key={r.id} className={`border-b border-line last:border-0 hover:bg-surface-2 ${rowClassName?.(r.original) ?? ""}`}>
                {r.getVisibleCells().map((c) => {
                  const meta = c.column.columnDef.meta as { hideSm?: boolean; align?: string } | undefined;
                  return (
                    <td key={c.id} className={`tabular whitespace-nowrap px-2 py-1.5 ${meta?.align === "left" ? "text-left" : "text-right"} ${meta?.hideSm ? "hidden sm:table-cell" : ""}`}>
                      {flexRender(c.column.columnDef.cell, c.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
            {table.getRowModel().rows.length === 0 && (
              <tr><td colSpan={columns.length} className="px-2 py-4 text-center text-ink-3">No rows match.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
