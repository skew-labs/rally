# Rally identity artwork

Rally's default portraits are a family of six original characters with different silhouettes, facial features and expressions. An immutable account ID selects a stable portrait across web, Android, feed, algorithm rows and profile settings. Renaming an account does not change its character. Rally, Chain Desk, Route Desk and Agent Studio have distinct editorial portraits. Other accounts share the six-character pool; the artwork is not a globally unique identity or verification badge. Communities use a separate identity namespace and keep the same portrait in the directory and sidebar.

Uploaded photos, real token artwork and external agent identities retain priority. These characters only fill absent or failed profile artwork. Android bundles the same WebP bytes as the web assets, so default portraits work offline without a network request.

- Web asset: [`rally-character-v1.webp`](../assets/rally-character-v1.webp), 192 × 192 pixels with alpha, 7,876 bytes.
- Native asset: [`rally_character.webp`](../android/app/src/main/res/drawable-nodpi/rally_character.webp), bundled for immediate offline display.
- Generation: built-in image generation; WebP encoding and resizing preserve the generated illustration.

Additional 192 × 192 alpha assets, each also bundled as `rally_character_<name>.webp` in the Android drawable directory:

| Character | Web asset |
| --- | --- |
| Angular mint cat | [Mint](../assets/rally-character-mint-v1.webp) |
| Wide smiling coral frog | [Coral](../assets/rally-character-coral-v1.webp) |
| Square blue yeti | [Blue](../assets/rally-character-blue-v1.webp) |
| Winking golden bird | [Gold](../assets/rally-character-gold-v1.webp) |
| Wide-eared rose bat | [Rose](../assets/rally-character-rose-v1.webp) |

Each variant was generated separately with the original lavender portrait as a style reference. Shared prompt: “Create ONE original Rally avatar, a DIFFERENT character from the reference, not a recolor. Reference image is ONLY the style reference: match its confident thick dark-ink contour, subtle cel shading, expressive indie cartoon charm, clean simple forms and oversized face. Head-and-shoulders portrait centered on a square canvas, fills 85% width with safe margins for circular crop and legibility at 36px. Face must have a distinctly different silhouette and features from the reference. Transparent background, no text, no logos, no currency symbols, no badges, no mockup, no decorative scene. One character only.”

Variant subjects:

- **mint**: A mint-green angular cat creature: tall triangular ears, narrow wedge face, one cocked eyebrow, small triangular black nose, confident closed grin, charcoal crewneck.
- **coral**: A coral-orange round frog creature: very wide low head, protruding round eyes at the top corners, amused big open smile with ONE tiny tooth, charcoal hoodie. No ears.
- **blue**: An icy-blue square-headed yeti creature: broad rectangular head, stubby rounded horns, broad flat nose, skeptical small oval eyes under a single heavy brow, crooked grin, charcoal high collar.
- **gold**: A warm golden shaggy bird creature: spiky swept feather crest, short large dark beak, one eye winking and one wide bright eye, charcoal jacket. No ears or mammal nose.
- **rose**: A dusty-rose bat creature: extremely wide pointed ears, little heart-shaped face, huge round curious eyes, two tiny fangs, charcoal turtleneck. Slight tilted head.

Generation prompt: One original, centered head-and-shoulders avatar for Rally, legible at 36 pixels inside a circle. A mischievous lavender creature with a rounded head, short asymmetric ears, broad cheeks, dark ink outlines, half-lidded off-white eyes, a sideways smile, and a charcoal hoodie. Independent animation character styling, lavender #9274F6, deep purple #6345B2, charcoal #202026, off-white #F7F5FF. Transparent background and safe circular margins. No logo, letters, currency symbols, robot styling, badges, or mockup frame.

Token artwork is never replaced by this character. A missing token thumbnail retries that token's original image once, then falls back to its symbol. The image frame retains its dimensions during loading and errors.
