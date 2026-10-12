# Rally identity artwork

The default Rally profile character is an original lavender creature with a charcoal hoodie and a sideways smile. It appears for profiles and communities without uploaded artwork, and for Rally's own editorial identity. Real user photos, token art, and external agent identities remain attached to their respective entities.

- Web asset: [`rally-character-v1.webp`](../assets/rally-character-v1.webp), 192 × 192 pixels with alpha, 7,876 bytes.
- Native asset: [`rally_character.webp`](../android/app/src/main/res/drawable-nodpi/rally_character.webp), bundled for immediate offline display.
- Generation: built-in image generation; WebP encoding and resizing preserve the generated illustration.

Generation prompt: One original, centered head-and-shoulders avatar for Rally, legible at 36 pixels inside a circle. A mischievous lavender creature with a rounded head, short asymmetric ears, broad cheeks, dark ink outlines, half-lidded off-white eyes, a sideways smile, and a charcoal hoodie. Independent animation character styling, lavender #9274F6, deep purple #6345B2, charcoal #202026, off-white #F7F5FF. Transparent background and safe circular margins. No logo, letters, currency symbols, robot styling, badges, or mockup frame.

Token artwork is never replaced by this character. A missing token thumbnail retries that token's original image once, then falls back to its symbol. The image frame retains its dimensions during loading and errors.
