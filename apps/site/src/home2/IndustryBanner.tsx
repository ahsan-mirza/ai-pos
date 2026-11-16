import { motion, useInView, useReducedMotion } from "framer-motion";
import { useRef } from "react";

const grocerySrc = "/images/home-2/supermarket.png";
const kitchenSrc = "/images/home-2/restaurant.png";

/**
 * Curves traced from the industry banner reference.
 * Both edges sweep from upper-right to lower-left: a rightward bow
 * through the upper half, then a softer return toward the bottom.
 * Coordinates are fractions of the banner box.
 */
const orangeClip = `M 0 0 H 0.448 C 0.510 0.16 0.300 0.78 0.324 1 H 0 Z`;
const groceryClip = `M 0.436 0 C 0.498 0.16 0.288 0.78 0.312 1 L 0.620 1 C 0.596 0.78 0.816 0.16 0.754 0 Z`;
const kitchenClip = `M 0.730 0 C 0.792 0.16 0.572 0.78 0.596 1 H 1 V 0 Z`;

const enter = { duration: 0.65, ease: [0.22, 1, 0.36, 1] as const };

export function IndustryBanner() {
  const reduce = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const inView = useInView(stageRef, { once: true, amount: 0.35 });
  const shown = Boolean(reduce) || inView;

  return (
    <section className="h2-industry" aria-labelledby="h2-industry-title">
      <div className="h2-industry-stage" ref={stageRef}>
        <svg className="h2-industry-defs" aria-hidden="true">
          <defs>
            <clipPath id="h2-industry-orange" clipPathUnits="objectBoundingBox">
              <path d={orangeClip} />
            </clipPath>
            <clipPath id="h2-industry-grocery" clipPathUnits="objectBoundingBox">
              <path d={groceryClip} />
            </clipPath>
            <clipPath id="h2-industry-kitchen" clipPathUnits="objectBoundingBox">
              <path d={kitchenClip} />
            </clipPath>
          </defs>
        </svg>

        <div className="h2-industry-photos">
          <motion.div
            className="h2-industry-photo is-kitchen"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: shown ? 1 : 0 }}
            transition={{ ...enter, delay: shown && !reduce ? 0.16 : 0 }}
          >
            <motion.img
              src={kitchenSrc}
              alt="Restaurant counter with an AxizPOS terminal and receipt printer"
              width={1774}
              height={887}
              loading="lazy"
              initial={reduce ? false : { scale: 1.06 }}
              animate={{ scale: shown || reduce ? 1 : 1.06 }}
              whileHover={reduce ? undefined : { scale: 1.045 }}
              transition={{ ...enter, delay: shown && !reduce ? 0.16 : 0 }}
            />
          </motion.div>
          <motion.div
            className="h2-industry-photo is-grocery"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: shown ? 1 : 0 }}
            transition={{ ...enter, delay: shown && !reduce ? 0.08 : 0 }}
          >
            <motion.img
              src={grocerySrc}
              alt="Supermarket checkout with an AxizPOS terminal and grocery basket"
              width={1774}
              height={887}
              loading="lazy"
              initial={reduce ? false : { scale: 1.06 }}
              animate={{ scale: shown || reduce ? 1 : 1.06 }}
              whileHover={reduce ? undefined : { scale: 1.045 }}
              transition={{ ...enter, delay: shown && !reduce ? 0.08 : 0 }}
            />
          </motion.div>
        </div>

        <motion.div
          className="h2-industry-panel"
          initial={reduce ? false : { opacity: 0, x: -22 }}
          animate={shown ? { opacity: 1, x: 0 } : { opacity: 0, x: -22 }}
          transition={enter}
        />

        <motion.svg
          className="h2-industry-strokes"
          viewBox="0 0 1000 1000"
          preserveAspectRatio="none"
          aria-hidden="true"
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: shown ? 1 : 0 }}
          transition={{ duration: 0.45, delay: shown && !reduce ? 0.2 : 0 }}
        >
          <path d="M 448 0 C 510 160 300 780 324 1000" />
          <path d="M 742 0 C 804 160 584 780 608 1000" />
        </motion.svg>

        <motion.div
          className="h2-industry-copy"
          initial={reduce ? false : { opacity: 0, x: -18 }}
          animate={shown ? { opacity: 1, x: 0 } : { opacity: 0, x: -18 }}
          transition={{ ...enter, delay: shown && !reduce ? 0.06 : 0 }}
        >
          <p className="h2-industry-kicker">Built for your industry</p>
          <h2 id="h2-industry-title">
            Powering Restaurants,
            <br />
            Supermarkets and More
          </h2>
          <p>Specialized POS workflows for restaurants, grocery stores, fashion, wholesale and high-volume businesses.</p>
          <motion.a
            className="h2-industry-cta"
            href="#solutions"
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={shown ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
            transition={{ duration: 0.45, delay: shown && !reduce ? 0.38 : 0, ease: enter.ease }}
          >
            Explore Solutions <span aria-hidden="true">→</span>
          </motion.a>
        </motion.div>
      </div>
    </section>
  );
}
