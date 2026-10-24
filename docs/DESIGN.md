# Dashboard design

The console is a warehouse control desk: the shelf feed is the main visual, with gate/session information in a horizontal status rail and actionable incidents below. Left aligned information supports scanning during a demo.

Tokens: dock navy #163b61, control blue #236caa, steel background #edf2f6, white #ffffff, safety amber #e2ad42, alarm red #ae393c. Barlow headings resemble industrial labels; Public Sans provides readable controls (Arial fallback when offline). No decorative animation. Only alarm and health changes demand attention.

Layout: `navigation | status rail / shelf feed + gate view / activity table`. On phones the navigation becomes a horizontal strip and the feeds stack. Reviewed against the brief: shelf state and active worker precede generic metrics, keeping the visual hierarchy specific to the gate/shelf system. A single blue control palette, an amber warehouse mark, and reserved red alarm banner avoid ornamental card grids.
