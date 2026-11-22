export interface DraftLine {
  key: string;
  service_id: string;
  quantity: string;
  garment_type: string;
  description: string;
  brand: string;
  colour: string;
  fabric: string;
  size: string;
  condition: string;
  stains: string;
  instructions: string;
  gross: string;
  tare: string;
}

export interface ServiceChoice {
  id: string;
  name: string;
  pricing_unit: string;
}

export function blankLine(serviceId: string): DraftLine {
  return {
    key: crypto.randomUUID(),
    service_id: serviceId,
    quantity: "1",
    garment_type: "",
    description: "",
    brand: "",
    colour: "",
    fabric: "",
    size: "",
    condition: "",
    stains: "",
    instructions: "",
    gross: "",
    tare: "",
  };
}

export function validateIntake(input: {
  customerId: string;
  lines: DraftLine[];
  services: ServiceChoice[];
  deposit: string;
  discount: string;
  canDiscount: boolean;
}): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!input.customerId) errors.customer = "Choose a customer.";
  if (input.lines.length === 0) errors.lines = "Add a garment or a weight bag.";
  for (const line of input.lines) {
    const service = input.services.find((row) => row.id === line.service_id);
    if (!service) {
      errors[`line-${line.key}-service`] = "Choose a service.";
      continue;
    }
    if (service.pricing_unit === "KG") {
      const gross = Number(line.gross);
      const tare = Number(line.tare || 0);
      if (!Number.isInteger(gross) || gross < 1) errors[`line-${line.key}-gross`] = "Enter the measured gross weight in grams.";
      if (!Number.isInteger(tare) || tare < 0) errors[`line-${line.key}-tare`] = "Enter the tare weight in grams.";
      if (Number.isInteger(gross) && Number.isInteger(tare) && tare > gross) errors[`line-${line.key}-tare`] = "Tare cannot be heavier than the gross weight.";
    } else {
      const quantity = Number(line.quantity);
      if (!Number.isInteger(quantity) || quantity < 1) errors[`line-${line.key}-quantity`] = "Quantity must be a whole number of at least 1.";
    }
  }
  if (input.deposit.trim() !== "") {
    const deposit = Number(input.deposit);
    if (!Number.isInteger(deposit) || deposit < 1) errors.deposit = "Enter the deposit in cents, as a whole number.";
  }
  if (input.discount.trim() !== "") {
    const discount = Number(input.discount);
    if (!input.canDiscount) errors.discount = "This register user cannot discount an order.";
    else if (!Number.isInteger(discount) || discount < 0) errors.discount = "Enter the discount in cents.";
  }
  return errors;
}

export function intakePayload(input: {
  clientId: string;
  storeId: string;
  customerId: string;
  orderType: string;
  promised: string;
  instructions: string;
  express: boolean;
  lines: DraftLine[];
  services: ServiceChoice[];
  deposit: string;
  discount: string;
}): Record<string, unknown> {
  const garments = input.lines.flatMap((line) => {
    const service = input.services.find((row) => row.id === line.service_id);
    if (service?.pricing_unit === "KG") return [];
    return [{
      service_id: line.service_id,
      quantity: Number(line.quantity || 1),
      garment_type: line.garment_type,
      description: line.description,
      brand: line.brand,
      colour: line.colour,
      fabric: line.fabric,
      size: line.size,
      condition: line.condition,
      stains: line.stains,
      instructions: line.instructions,
    }];
  });
  const bags = input.lines.flatMap((line) => {
    const service = input.services.find((row) => row.id === line.service_id);
    if (service?.pricing_unit !== "KG") return [];
    return [{ service_id: line.service_id, gross_weight: Number(line.gross || 0), tare_weight: Number(line.tare || 0) }];
  });
  const deposit = Number(input.deposit || 0);
  const discount = Number(input.discount || 0);
  return {
    id: input.clientId,
    idempotency_key: input.clientId,
    intake_store_id: input.storeId,
    customer_id: input.customerId,
    order_type: input.orderType,
    promised_at: input.promised ? new Date(input.promised).toISOString() : null,
    instructions: input.instructions,
    express: input.express,
    discount_cents: Number.isInteger(discount) && discount > 0 ? discount : 0,
    garments,
    bags,
    deposit: deposit > 0 ? { amount_cents: deposit, method: "cash" } : null,
  };
}

export function intakeCounts(lines: DraftLine[], services: ServiceChoice[]): { garments: number; bags: number; weight: number } {
  let garments = 0;
  let bags = 0;
  let weight = 0;
  for (const line of lines) {
    const service = services.find((row) => row.id === line.service_id);
    if (service?.pricing_unit === "KG") {
      bags += 1;
      const gross = Number(line.gross || 0);
      const tare = Number(line.tare || 0);
      if (Number.isInteger(gross) && Number.isInteger(tare)) weight += Math.max(0, gross - tare);
    } else {
      const quantity = Number(line.quantity || 0);
      if (Number.isInteger(quantity)) garments += quantity;
    }
  }
  return { garments, bags, weight };
}
