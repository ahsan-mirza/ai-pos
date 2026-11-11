export interface ProductAttribute {
  id: string;
  key: string;
  name: string;
  description: string;
  data_type: string;
  unit: string;
  options: string[];
  required: boolean;
  searchable: boolean;
  filterable: boolean;
  active: boolean;
  sort_order: number;
  origin: string;
}
