import { IMAGE_SETS } from "./image-sets";

const CITY = "/images/home-2/isometric-city.png";
const SIZES = "(max-width: 860px) calc(100vw - 48px), min(1400px, calc(100vw - 48px))";

export function staticHeroHtml(): string {
  const set = IMAGE_SETS[CITY];
  return `<div id="h2-static-hero" class="home2">
      <a class="h2-skip" href="#h2-main">Skip to content</a>
      <div id="h2-header-slot">
        <header class="h2-nav">
          <div class="h2-nav-bar">
            <a class="h2-logo" href="/" aria-label="AxizPOS home"><img src="/brand/logo.svg" alt="" width="132" height="32" /></a>
          </div>
        </header>
      </div>
      <main id="h2-main">
        <section class="h2-hero">
          <div class="h2-hero-copy">
            <p class="h2-eyebrow"><span></span>Smart POS for every business<span></span></p>
            <h1><span class="h2-h1-lines">Run <span class="h2-h1-your">your</span><br />business <span class="h2-h1-break">better</span></span><span class="h2-h1-brand">with AxizPOS</span></h1>
            <div id="h2-rotator-slot">
              <div class="h2-rotator">
                <article class="h2-slide">
                  <h2>Cafe POS Software</h2>
                  <p>Manage cafe billing, menu items, recipes, ingredients, inventory and daily cafe operations with one intelligent POS platform.</p>
                  <ul>
                    <li>Cafe POS UAE</li>
                    <li>Coffee Shop POS</li>
                    <li>Cafe Billing Software</li>
                    <li>Cafe Inventory Management</li>
                  </ul>
                </article>
                <div class="h2-tabs">
                  <button type="button" aria-selected="true">Cafe</button>
                  <button type="button">Restaurant</button>
                  <button type="button">Supermarket</button>
                  <button type="button">Electronics</button>
                  <button type="button">Fashion</button>
                  <button type="button">Quick Service</button>
                </div>
              </div>
            </div>
            <a class="h2-btn" href="/explore">Explore AxizPOS <span aria-hidden="true">→</span></a>
          </div>
          <div class="h2-stage">
            <div class="h2-city">
              <picture id="h2-city-picture">
                <source type="image/avif" srcset="${set.avif}" sizes="${SIZES}" />
                <source type="image/webp" srcset="${set.webp}" sizes="${SIZES}" />
                <img src="${CITY}" alt="Cafe, restaurant, retail, supermarket, electronics and wholesale storefronts" width="1691" height="691" sizes="${SIZES}" fetchpriority="high" loading="eager" />
              </picture>
              <div id="h2-pins-slot"></div>
            </div>
            <div id="h2-devices-slot"></div>
          </div>
        </section>
        <div id="h2-below-slot"></div>
      </main>
    </div>`;
}
