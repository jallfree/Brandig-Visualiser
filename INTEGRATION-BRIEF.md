# Branding Visualiser — Next.js Integration Brief

## What This Is
A client-side branding visualiser that lets users upload artwork (PNG, JPEG, PDF) and see it applied to product images with perspective correction. Everything runs in the browser — no server-side processing needed.

The standalone version lives at `/Users/justinmacmini/Branding Visualiser/` and runs on Flask (for local development only). This brief describes how to integrate it into the Rhino Next.js website.

---

## Current Standalone Architecture

### Core Engine (customizer.html — all inline JS)
The perspective engine does the following:
1. Loads a base product photo (2000x2000 PNG)
2. Loads mask PNGs per branding area (front, side, canopy, glass) — alpha channel defines the clipping region
3. Loads an overlay PNG (shadows/highlights composited on top for realism)
4. Loads corner coordinates — 4 points per area in TL, TR, BR, BL order
5. When user drops artwork, it maps the artwork to the config corners using a homography (perspective transform)
6. Clips the warped artwork to the mask region
7. Draws: base image → warped artwork (clipped) → overlay
8. User can drag corner handles to fine-tune
9. Downloads the result as a 2000x2000 PNG

### Key Functions to Port
These are all in `customizer.html` and should become utility functions in the React component:

- `computeHomography(srcCorners, dstCorners)` — computes 8-parameter perspective transform matrix
- `inverseHomography(h)` — inverts the matrix for reverse mapping
- `applyHomography(h, x, y)` — applies transform to a point
- `drawPerspectiveArtwork(artwork, artworkCorners)` — renders artwork with perspective warp using bilinear interpolation
- `extractPanelMask(overlayImg)` — converts mask PNG alpha channel to binary array
- `extractClipPath(maskData)` — traces the mask edge into a polygon path for canvas clipping
- `findPanelCorners(maskData)` — extracts 4 corner points from mask (fallback when no coordinates provided)
- `initArtworkCorners(panelCorners, artWidth, artHeight)` — creates centered rectangle placement (fallback)

### Branding Assets Per Product
Each product that supports the visualiser needs these files. All images are 2000x2000px PNGs:

- **Base image** (`main.png`) — clean product photo
- **Mask PNGs** (one per branding area) — white on transparent, defining the clipping region (e.g. `mask-front.png`, `mask-side.png`, `mask-canopy.png`, `mask-glass.png`)
- **Overlay** (`overlay.png`) — shadow/highlight layer composited on top for realism
- **Corner coordinates** — 4 XY points per branding area defining where artwork maps to

Not every product has every mask — only the areas defined for that product.

### Corner Coordinate Format
Each branding area needs 4 corner coordinates in **clockwise order: Top-Left, Top-Right, Bottom-Right, Bottom-Left**. Coordinates are pixel positions on the 2000x2000 canvas.

Example for SCOOP 3FF:
```
Front: TL(567,1007) TR(1785,755) BR(1785,1560) BL(567,1904)
Side:  TL(213,751)  TR(567,1007) BR(567,1904)  BL(212,1541)
```

These are measured in Photoshop using the Info panel (F8) at each corner of the branding panel.

---

## Integration Plan for Rhino Website

### 1. PIM Feed — Source of All Branding Data

All branding visualiser data comes from the PIM system, just like regular product data. The PIM stores:

- **Branding images**: base image, mask PNGs, overlay PNG (uploaded to PIM per product)
- **Corner coordinates**: XY coordinates per branding area (stored as fields in PIM per product)
- **Area definitions**: which branding areas the product supports (front, side, canopy, glass)

This means:
- No manual file management on the website
- Adding branding support to a new product = add data in PIM, run sync
- The sync script handles downloading images and building the data structure

### 2. Sync Script — scripts/sync-products.ts

The existing sync script already handles product images. Extend it to also sync branding data:

**Images**: Download branding images into `public/products/{order-code-slug}/branding/`:
```
public/products/{order-code-slug}/branding/
├── main.png
├── mask-front.png
├── mask-side.png
├── overlay.png
```

**Data**: The corner coordinates and area definitions get written into the product data in `src/data/products/index.json`. Each product that supports branding would have a `branding` field:

```json
{
  "order_code": "SCOOP-3FF",
  "model_name": "Scoop 3FF",
  "branding": {
    "areas": {
      "front": {
        "corners": [[567, 1007], [1785, 755], [1785, 1560], [567, 1904]]
      },
      "side": {
        "corners": [[213, 751], [567, 1007], [567, 1904], [212, 1541]]
      }
    },
    "images": {
      "main": "branding/main.png",
      "overlay": "branding/overlay.png",
      "mask-front": "branding/mask-front.png",
      "mask-side": "branding/mask-side.png"
    }
  }
}
```

Products without branding support simply don't have the `branding` field — no flag needed.

**Image manifest**: Update `src/data/products/manifest.json` to include branding image paths alongside regular product images.

### 3. Data Layer — src/lib/pim.ts

Add functions to access branding data:

```typescript
// Check if a product has branding visualiser support
export function hasBrandingVisualiser(product: Product): boolean {
  return !!product.branding && Object.keys(product.branding.areas).length > 0;
}

// Get branding config for a product
export function getBrandingConfig(product: Product): BrandingConfig | null {
  return product.branding || null;
}
```

No filesystem checks needed — it's all in the synced JSON data.

### 4. TypeScript Types — src/types/product.ts

```typescript
export interface BrandingAreaConfig {
  corners: [number, number][]; // TL, TR, BR, BL — pixel coords on 2000x2000 canvas
}

export interface BrandingConfig {
  areas: Record<string, BrandingAreaConfig>;
  images: Record<string, string>; // image key → relative path
}

export interface BrandingVisualiserProps {
  productName: string;
  productSlug: string;
  config: BrandingConfig;
}
```

### 5. React Component — src/components/product/BrandingVisualiser.tsx

This is a `'use client'` component. It receives the branding config as props (passed from the server component page).

Key implementation notes:

- **Canvas ref**: Use `useRef<HTMLCanvasElement>` for the 2000x2000 canvas
- **State**: Use `useState` for artwork per area, active area, drag state
- **Image loading**: Use `fetch()` + `createImageBitmap()` to load product images from `/products/{slug}/branding/`
- **File upload**: Standard `<input type="file">` with drag-and-drop. Cap at 10MB. Accept `image/png, image/jpeg, application/pdf`
- **PDF support**: Dynamic import of pdf.js: `const pdfjsLib = await import('pdfjs-dist')`
- **Perspective engine**: Port the homography functions as-is — they're pure math, no DOM dependencies
- **Download**: `canvas.toDataURL('image/png')` → download link
- **Mobile**: Hide corner drag handles on mobile. Auto-fit only. Use `window.matchMedia` or Tailwind breakpoints
- **Styling**: Use Tailwind classes matching Rhino site design (Outfit headings, DM Sans body, site colour palette)

Structure:
```
src/components/product/
├── BrandingVisualiser.tsx        # Main 'use client' component
├── branding/
│   ├── useBrandingEngine.ts     # Custom hook: canvas rendering, homography, drag handling
│   ├── perspective.ts           # Pure functions: computeHomography, inverseHomography, etc.
│   ├── masks.ts                 # Pure functions: extractPanelMask, extractClipPath, findPanelCorners
│   └── ArtworkUploader.tsx      # Upload drop zone sub-component
```

### 6. Product Detail Page Integration

In `src/app/products/[category]/[modelSlug]/page.tsx`:

```typescript
import { hasBrandingVisualiser, getBrandingConfig } from '@/lib/pim';

// Inside the page component (server component):
const hasBranding = hasBrandingVisualiser(product);
const brandingConfig = hasBranding ? getBrandingConfig(product) : null;

// In the JSX, add a button that opens the visualiser:
{hasBranding && brandingConfig && (
  <BrandingVisualiserButton
    productName={product.model_name}
    productSlug={getProductSlug(product.model_name)}
    config={brandingConfig}
  />
)}
```

The button could either:
- **Option A**: Open a modal/overlay (keeps user on the product page) — recommended
- **Option B**: Navigate to `/products/{category}/{slug}/branding` (dedicated page)

### 7. Image Paths

The component resolves image paths from the config data:

```typescript
const basePath = `/products/${productSlug}`;
const mainImageUrl = `${basePath}/${config.images.main}`;
const maskUrl = (area: string) => `${basePath}/${config.images[`mask-${area}`]}`;
const overlayUrl = `${basePath}/${config.images.overlay}`;
```

### 8. File Size Validation

Add client-side validation before processing uploads:

```typescript
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'application/pdf'];

function validateFile(file: File): string | null {
  if (!ALLOWED_TYPES.includes(file.type)) return 'Please upload a PNG, JPEG, or PDF file';
  if (file.size > MAX_FILE_SIZE) return 'File size must be under 10MB';
  return null; // Valid
}
```

### 9. Mobile Considerations

- On viewports < 768px: hide corner handles, remove "Adjust Artwork" section
- Auto-fit only — artwork maps to config corners with no manual adjustment
- Make drop zones full-width and taller for easier touch targets
- Download button should be prominent
- Consider whether PDF upload is needed on mobile (pdf.js is ~500KB)

### 10. Performance / Loading

- Lazy-load the branding visualiser component (dynamic import with `next/dynamic`)
- Show a loading skeleton while product images load

### 11. Image Optimisation — AVIF Conversion

The 2000x2000 PNGs are the heaviest assets. Convert to AVIF during sync to cut load times significantly.

**Which images to convert:**

| Image | Convert to AVIF? | Why |
|-------|-------------------|-----|
| main (base product photo) | **Yes** | Biggest file (~2-5MB as PNG → ~500KB-1MB as AVIF). No alpha channel dependency. Biggest win. |
| overlay (shadows/highlights) | **No** — keep PNG | Uses alpha channel for transparency blending. Lossy compression would damage the subtle shadow gradients. |
| masks (mask-front, mask-side, etc.) | **No** — keep PNG | Alpha channel must be pixel-perfect — the code reads every pixel's alpha to build clipping paths. Lossy would corrupt mask edges. Already small files (~100-500KB). |

**Sync script conversion** — Sharp already handles product image optimisation. Add AVIF output for the base image:

```typescript
// In sync script, after downloading branding base image:
await sharp(inputPath).avif({ quality: 80 }).toFile(avifOutputPath);
// Keep the PNG as fallback for older browsers
```

**Browser fallback** — AVIF support is ~95%+ (Safari 16.4+, Chrome 85+, Firefox 93+). Use a simple check in the component:

```typescript
// Check AVIF support once on load
async function supportsAvif(): Promise<boolean> {
  const img = new Image();
  return new Promise(resolve => {
    img.onload = () => resolve(img.width > 0);
    img.onerror = () => resolve(false);
    img.src = 'data:image/avif;base64,AAAAIGZ0eXBhdmlmAAAAAGF2aWZtaWYxbWlhZk1BMUIAAADybWV0YQAAAAAAAAAoaGRscgAAAAAAAAAAcGljdAAAAAAAAAAAAAAAAGxpYmF2aWYAAAAADnBpdG0AAAAAAAEAAAAeaWxvYwAAAABEAAABAAEAAAABAAABGgAAAB0AAAAoaWluZgAAAAAAAQAAABppbmZlAgAAAAABAABhdjAxQ29sb3IAAAAAamlwcnAAAABLaXBjbwAAABRpc3BlAAAAAAAAAAIAAAACAAAAEHBpeGkAAAAAAwgICAAAAAxhdjFDgQ0MAAAAABNjb2xybmNseAACAAIAAYAAAAAXaXBtYQAAAAAAAAABAAEEAQKDBAAAACVtZGF0EgAKCBgANogQEAwgMg8f8D///8WfhwB8+ErU42Y=';
  });
}

// Then load the appropriate format:
const useAvif = await supportsAvif();
const mainImageUrl = `${basePath}/main.${useAvif ? 'avif' : 'png'}`;
```

**Expected improvement**: Total initial load drops from ~5-7MB to ~2-3MB. Page-ready time improves from ~3-4 seconds to ~1-2 seconds on a decent connection.

**Manifest update**: The image manifest should list both formats so the component knows what's available:

```json
{
  "branding": {
    "main": "branding/main.png",
    "main-avif": "branding/main.avif",
    "overlay": "branding/overlay.png",
    "mask-front": "branding/mask-front.png",
    "mask-side": "branding/mask-side.png"
  }
}
```

---

## PIM Setup Guide

For each product you want to add branding support to:

1. **Create the images in Photoshop** (all 2000x2000px PNG):
   - Base product photo (clean, no branding)
   - One mask per branding area (white shape on transparent background marking where branding goes)
   - Overlay with shadows/highlights that sit on top of the branding

2. **Measure corner coordinates in Photoshop**:
   - Open the base image
   - Use the Info panel (F8)
   - Hover over each corner of each branding area
   - Note the X,Y pixel coordinates
   - Order: Top-Left, Top-Right, Bottom-Right, Bottom-Left (clockwise)
   - Where two panels share an edge (e.g. front meets side), the shared corners should have matching coordinates

3. **Upload to PIM**:
   - Upload the branding images to the product record
   - Enter the corner coordinates for each branding area
   - Mark which areas the product supports (front, side, canopy, glass)

4. **Run sync**: `npm run sync` — the script downloads everything and rebuilds the data

---

## Testing Checklist

1. Product with branding data in PIM shows "Branding Visualiser" button on website
2. Product without branding data does NOT show the button
3. Visualiser loads and displays the product image correctly
4. Dropping PNG artwork auto-fits to the defined corners
5. Dropping JPEG artwork works
6. Dropping PDF artwork works (renders first page)
7. File over 10MB shows error message
8. Invalid file type shows error message
9. Corner handles are draggable for fine-tuning (desktop only)
10. Re-uploading artwork resets to the PIM-defined corners
11. "Clear" removes artwork from an area
12. Download produces a 2000x2000 PNG with branding applied (no handles visible)
13. Multiple areas can have different artwork simultaneously
14. Mobile: auto-fit only, no drag handles, usable touch targets
15. Overlay (shadows/highlights) renders on top of artwork
16. After PIM data change + re-sync, website reflects updated corners/images

---

## Reference Files

All source code for the standalone version:
- **Engine + UI**: `/Users/justinmacmini/Branding Visualiser/customizer.html` (all inline — ~1300 lines)
- **Server (not needed for Next.js)**: `/Users/justinmacmini/Branding Visualiser/server.py`
- **Product data**: `/Users/justinmacmini/Branding Visualiser/products.json`
- **Example config**: `/Users/justinmacmini/Branding Visualiser/products/scoop-3ff/config.json`
- **Example branding assets**: `/Users/justinmacmini/Branding Visualiser/products/scoop-3ff/`

GitHub repo: https://github.com/jallfree/Brandig-Visualiser
