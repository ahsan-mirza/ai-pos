import { aiPos } from "./posts/ai.ts";
import { aiChangingPos, aiVsTraditional, whatIsAiPos } from "./posts/aiGuides.ts";
import { bestPos } from "./posts/best.ts";
import { billingVsPos } from "./posts/billing.ts";
import { cloudVsOnPrem, offlineSoftware, smallBusinessPos } from "./posts/buyingGuides.ts";
import { toPages } from "./guide.ts";
import { electronicsStore, fashionPos, groceryPos, restaurantAutomation, retailPos, wholesaleSoftware } from "./posts/industryGuides.ts";
import { aiInventory, demandForecast, posAnalytics } from "./posts/inventoryGuides.ts";
import { offlinePos } from "./posts/offline.ts";
import { integration, lossPrevention, multiStore } from "./posts/operationsGuides.ts";
import { restaurantPos } from "./posts/restaurant.ts";
import { stockLoss } from "./posts/stock.ts";
import { supermarketInventory } from "./posts/supermarket.ts";
import { wholesalePos } from "./posts/wholesale.ts";

const guides = [
  bestPos,
  restaurantPos,
  supermarketInventory,
  billingVsPos,
  stockLoss,
  wholesalePos,
  offlinePos,
  aiPos,
  whatIsAiPos,
  aiVsTraditional,
  aiChangingPos,
  smallBusinessPos,
  cloudVsOnPrem,
  offlineSoftware,
  aiInventory,
  posAnalytics,
  demandForecast,
  multiStore,
  integration,
  lossPrevention,
  retailPos,
  restaurantAutomation,
  groceryPos,
  wholesaleSoftware,
  electronicsStore,
  fashionPos,
].map(toPages);

export const ENGLISH_GUIDES = guides.map((pair) => pair.en);
export const ARABIC_GUIDES = guides.map((pair) => pair.ar);
