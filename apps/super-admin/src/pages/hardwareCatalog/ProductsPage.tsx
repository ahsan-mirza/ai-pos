import { DataTable, type DataTableColumn } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader } from "../../components/PageHeader";
import { ErrorNote, GhostButton } from "../../components/ui";
import { api, errorText } from "../../lib/api";
import { money, when } from "../../lib/format";
import { useSession } from "../../lib/session";
import { stockLabel, type CatalogProduct } from "./types";

export function HardwareProductsPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const navigate = useNavigate();
  const [rows, setRows] = useState<CatalogProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = new URLSearchParams({ offset: String((page - 1) * pageSize), limit: String(pageSize) });
    if (query.trim()) params.set("q", query.trim());
    if (status) params.set("status", status);
    setLoading(true);
    api
      .page<CatalogProduct>(`/hardware-catalog/products?${params}`)
      .then((found) => {
        setRows(found.rows);
        setTotal(found.total);
      })
      .catch((caught) => setError(errorText(caught, "Products could not be loaded.")))
      .finally(() => setLoading(false));
  }, [page, pageSize, query, status]);

  const columns: DataTableColumn<CatalogProduct>[] = [
    {
      id: "image",
      header: "Image",
      cell: (row) => {
        const image = row.images.find((item) => item.is_primary) ?? row.images[0];
        return image ? <img src={image.thumb_url} alt="" className="h-10 w-10 rounded-lg object-cover" /> : <span className="text-charcoal/40">—</span>;
      },
    },
    { id: "name", header: "Name", cell: (row) => row.name },
    { id: "sku", header: "SKU", cell: (row) => row.sku },
    { id: "category", header: "Category", cell: (row) => row.category_name },
    { id: "brand", header: "Brand", cell: (row) => row.brand || "—" },
    { id: "model", header: "Model", cell: (row) => row.model_number || "—" },
    { id: "price", header: "Selling price", cell: (row) => (row.display_price_fils == null ? "On request" : money(row.display_price_fils, row.currency)) },
    { id: "currency", header: "Currency", cell: (row) => row.currency },
    { id: "stock", header: "Availability", cell: (row) => stockLabel(row.stock_status) },
    { id: "status", header: "Publishing", cell: (row) => (row.archived ? "Archived" : row.is_published ? "Published" : "Draft") },
    { id: "updated", header: "Updated", cell: (row) => when(row.updated_at) },
    {
      id: "actions",
      header: "Actions",
      cell: (row) => (
        <GhostButton onClick={() => navigate(`/hardware-catalog/products/${row.id}`)}>{admin ? "Edit" : "View"}</GhostButton>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Products"
        description="Devices shown on the public hardware catalogue. Cost prices stay in the console."
        controls={
          admin ? (
            <Link to="/hardware-catalog/products/new" className="inline-flex h-10 items-center rounded-full bg-accent px-5 text-sm font-medium text-white">
              New product
            </Link>
          ) : null
        }
      />
      <ErrorNote message={error} />
      <div className="mb-4 flex flex-wrap gap-2">
        <input aria-label="Search products" value={query} onChange={(event) => { setPage(1); setQuery(event.target.value); }} placeholder="Search name, SKU, or brand" className="h-10 w-full max-w-xs rounded-xl border border-line px-3 text-sm" />
        <select aria-label="Publishing status" value={status} onChange={(event) => { setPage(1); setStatus(event.target.value); }} className="h-10 rounded-xl border border-line px-3 text-sm">
          <option value="">All statuses</option>
          <option value="published">Published</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>
      </div>
      <DataTable
        aria-label="Hardware products"
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        isLoading={loading && rows.length === 0}
        minWidth="1100px"
        emptyState={{ title: "No products", description: "Create a product to publish it on the website." }}
        pagination={{
          mode: "server",
          currentPage: page,
          pageSize,
          totalRecords: total,
          onPageChange: setPage,
          onPageSizeChange: (size) => {
            setPageSize(size);
            setPage(1);
          },
        }}
      />
    </div>
  );
}
