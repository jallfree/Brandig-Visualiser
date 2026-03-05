# BrandReady — Implementation Instructions for Next.js Website

## 1. What You Are Building

BrandReady is a client-side branding visualiser that opens as a **modal overlay** on product detail pages. Users upload artwork (PNG, JPEG, or PDF), and the component perspective-warps it onto a product photo, clips it to the branding panel shape using mask PNGs, and composites shadow/highlight overlays for realism. Users can drag corner handles on desktop to fine-tune positioning, then download a 2000×2000 PNG of the result.

**Key facts:**
- 100% browser-side — no server-side image processing, no API routes needed
- All data comes from PIM sync — the component reads static JSON and locally-synced images
- Different products have different branding areas (e.g. a chest freezer might only have front + left side, a display fridge might have front + glass door + canopy)
- The UI dynamically shows only the areas that exist for each product

**Deliverables:**
1. TypeScript type additions to `src/types/product.ts`
2. Sync script extension in `scripts/sync-products.ts`
3. Data layer helpers in `src/lib/pim.ts`
4. Client component tree in `src/components/product/brandready/`
5. Product detail page integration point

---

## 2. PIM Data Contract

Each product in the PIM feed has a `brandready` field. Here is the exact structure:

```json
"brandready": {
  "images": {
    "brandready_main_image": "https://pim.rhinoequipment.org/api/feed/files/Products/SCOOP300-7S-FF-WW-GB/BrandReady/scoop-300ff-main-image.png",
    "brandready_front_panel": "https://pim.rhinoequipment.org/api/feed/files/Products/SCOOP300-7S-FF-WW-GB/BrandReady/scoop-300ff-front.png",
    "brandready_lh_side": "https://pim.rhinoequipment.org/api/feed/files/Products/SCOOP300-7S-FF-WW-GB/BrandReady/scoop-300ff-lh-side.png",
    "brandready_overlay": "https://pim.rhinoequipment.org/api/feed/files/Products/SCOOP300-7S-FF-WW-GB/BrandReady/scoop-300ff-overlay.png"
  },
  "coordinates": {
    "front_panel": {
      "top_left": { "x": 567, "y": 1007 },
      "top_right": { "x": 1785, "y": 755 },
      "bottom_left": { "x": 567, "y": 1904 },
      "bottom_right": { "x": 1785, "y": 1560 }
    },
    "lh_side": {
      "top_left": { "x": 213, "y": 751 },
      "top_right": { "x": 567, "y": 1007 },
      "bottom_left": { "x": 212, "y": 1541 },
      "bottom_right": { "x": 567, "y": 1904 }
    },
    "rh_side": {
      "top_left": { "x": null, "y": null },
      "top_right": { "x": null, "y": null },
      "bottom_left": { "x": null, "y": null },
      "bottom_right": { "x": null, "y": null }
    },
    "light_canopy": {
      "top_left": { "x": null, "y": null },
      "top_right": { "x": null, "y": null },
      "bottom_left": { "x": null, "y": null },
      "bottom_right": { "x": null, "y": null }
    },
    "door_glass": {
      "top_left": { "x": null, "y": null },
      "top_right": { "x": null, "y": null },
      "bottom_left": { "x": null, "y": null },
      "bottom_right": { "x": null, "y": null }
    }
  }
}
```

### Area Mapping Table

| PIM coordinate key | PIM mask image key | Display name | Example products |
|---|---|---|---|
| `front_panel` | `brandready_front_panel` | Front Panel | Most products |
| `lh_side` | `brandready_lh_side` | Left Side | Chest freezers, some fridges |
| `rh_side` | `brandready_rh_side` | Right Side | Some fridges |
| `light_canopy` | `brandready_light_canopy` | Light Canopy | Display fridges |
| `door_glass` | `brandready_door_glass` | Door Glass | Glass-door fridges |

### Rules for Determining Active Areas

An area is **active** for a product only when BOTH of these conditions are true:
1. The coordinates for that area have **non-null** x/y values
2. A corresponding mask image exists in `brandready.images`

**Only active areas get upload drop zones in the UI.** A product with only front_panel and lh_side data will show exactly 2 upload zones. A product with front_panel, door_glass, and light_canopy will show 3.

### Coordinate System
- All coordinates are **pixel positions on a 2000×2000 canvas**
- Values are **numbers** (not strings)
- Corner order for the engine: **TL, TR, BR, BL** (clockwise from top-left)
- PIM provides `top_left`, `top_right`, `bottom_right`, `bottom_left` — convert to array: `[TL, TR, BR, BL]`
- Safety: parse with `Number()` as a fallback in case any values arrive as strings

---

## 3. Sync Script Extension

**File:** `scripts/sync-products.ts`

### CRITICAL: Do NOT Resize BrandReady Images

The existing sync script runs all product images through sharp with a max width of 1200px. **BrandReady images must bypass this.** Reasons:
- The canvas operates at 2000×2000 — coordinates are calibrated to that resolution
- Mask PNGs require pixel-perfect alpha channels — lossy compression destroys mask edges
- The overlay PNG uses alpha transparency for shadow blending — compression damages it

### Download Logic

When processing each product, check if `product.brandready?.images` has entries. If so:

1. Create directory: `public/products/{slug}/brandready/`
2. Download each BrandReady image **without sharp optimisation**
3. Map PIM image keys to local filenames:

| PIM image key | Local filename |
|---|---|
| `brandready_main_image` | `main.png` |
| `brandready_front_panel` | `mask-front_panel.png` |
| `brandready_lh_side` | `mask-lh_side.png` |
| `brandready_rh_side` | `mask-rh_side.png` |
| `brandready_light_canopy` | `mask-light_canopy.png` |
| `brandready_door_glass` | `mask-door_glass.png` |
| `brandready_overlay` | `overlay.png` |

4. For the main image **only**: also generate an AVIF version using `sharp(inputPath).avif({ quality: 80 }).toFile(avifPath)` — this is the one optimisation allowed, for faster loading. Keep the PNG as fallback.

5. Follow the same incremental pattern as existing images: skip if file already exists and has non-zero size.

### Pseudocode

```typescript
// Inside the per-product loop, after existing image downloads:
if (product.brandready?.images) {
  const brandreadyDir = path.join(productImageDir, 'brandready');
  fs.mkdirSync(brandreadyDir, { recursive: true });

  for (const [key, url] of Object.entries(product.brandready.images)) {
    if (!url) continue;

    // Map PIM key to local filename
    let localName: string;
    if (key === 'brandready_main_image') localName = 'main.png';
    else if (key === 'brandready_overlay') localName = 'overlay.png';
    else localName = `mask-${key.replace('brandready_', '')}.png`;

    const destPath = path.join(brandreadyDir, localName);

    if (fs.existsSync(destPath) && fs.statSync(destPath).size > 0) {
      continue; // Skip existing
    }

    await downloadFile(url, destPath);
    // NO sharp optimisation — download raw

    // Generate AVIF for main image only
    if (key === 'brandready_main_image') {
      const avifPath = path.join(brandreadyDir, 'main.avif');
      await sharp(destPath).avif({ quality: 80 }).toFile(avifPath);
    }
  }
}
```

### Manifest Update

Add BrandReady image entries to `src/data/products/manifest.json`. Under each product's order code, add entries like:

```json
"brandready_main": "/products/{slug}/brandready/main.png",
"brandready_main_avif": "/products/{slug}/brandready/main.avif",
"brandready_overlay": "/products/{slug}/brandready/overlay.png",
"brandready_mask_front_panel": "/products/{slug}/brandready/mask-front_panel.png",
"brandready_mask_lh_side": "/products/{slug}/brandready/mask-lh_side.png"
```

---

## 4. TypeScript Types

**File:** `src/types/product.ts`

Add these interfaces:

```typescript
export interface BrandReadyCornerPoint {
  x: number;
  y: number;
}

export interface BrandReadyAreaCoords {
  top_left: BrandReadyCornerPoint;
  top_right: BrandReadyCornerPoint;
  bottom_left: BrandReadyCornerPoint;
  bottom_right: BrandReadyCornerPoint;
}

export interface BrandReadyData {
  images: Record<string, string | null>;
  coordinates: Record<string, BrandReadyAreaCoords>;
}
```

Add to the existing `Product` interface:

```typescript
brandready?: BrandReadyData;
```

Add the props interface for the component:

```typescript
export interface BrandReadyModalProps {
  isOpen: boolean;
  onClose: () => void;
  productName: string;
  orderCodeSlug: string;
  brandready: BrandReadyData;
}
```

---

## 5. Data Layer Helpers

**File:** `src/lib/pim.ts`

```typescript
/**
 * Check if a product has BrandReady support.
 * Requires at least one area with both non-null coordinates AND a corresponding mask image.
 */
export function hasBrandReady(product: Product): boolean {
  if (!product.brandready) return false;
  const { images, coordinates } = product.brandready;
  if (!images || !coordinates) return false;

  return Object.entries(coordinates).some(([areaKey, coords]) => {
    const hasCoords = coords.top_left.x !== null && coords.top_left.y !== null;
    const maskKey = `brandready_${areaKey}`;
    const hasMask = !!images[maskKey];
    return hasCoords && hasMask;
  });
}

/**
 * Get the list of active BrandReady areas for a product.
 * Returns only areas that have both valid coordinates and a mask image.
 */
export function getBrandReadyAreas(product: Product): string[] {
  if (!product.brandready) return [];
  const { images, coordinates } = product.brandready;
  if (!images || !coordinates) return [];

  return Object.entries(coordinates)
    .filter(([areaKey, coords]) => {
      const hasCoords = coords.top_left.x !== null && coords.top_left.y !== null;
      const maskKey = `brandready_${areaKey}`;
      const hasMask = !!images[maskKey];
      return hasCoords && hasMask;
    })
    .map(([areaKey]) => areaKey);
}
```

---

## 6. Perspective Engine

**File:** `src/components/product/brandready/perspective.ts`

This is the mathematical core. These are **pure functions** — no DOM dependencies, no React, no side effects. They work identically in TypeScript.

```typescript
// ============================================================
// BrandReady Perspective Engine
// Pure math functions for homography-based perspective warping
// ============================================================

export interface Point {
  x: number;
  y: number;
}

export interface MaskData {
  mask: Uint8Array;
  width: number;
  height: number;
}

/**
 * Compute an 8-parameter homography matrix that maps 4 source corners
 * to 4 destination corners using Gaussian elimination.
 *
 * @param srcCorners - 4 source points [TL, TR, BR, BL]
 * @param dstCorners - 4 destination points [TL, TR, BR, BL]
 * @returns 9-element homography array (h[8] = 1)
 */
export function computeHomography(srcCorners: Point[], dstCorners: Point[]): number[] {
  const A: number[][] = [];
  for (let i = 0; i < 4; i++) {
    const sx = srcCorners[i].x, sy = srcCorners[i].y;
    const dx = dstCorners[i].x, dy = dstCorners[i].y;
    A.push([-sx, -sy, -1, 0, 0, 0, sx * dx, sy * dx, dx]);
    A.push([0, 0, 0, -sx, -sy, -1, sx * dy, sy * dy, dy]);
  }
  const n = 8;
  const aug = A.map(row => [...row.slice(0, 8), -row[8]]);
  for (let col = 0; col < n; col++) {
    let maxRow = col;
    for (let row = col + 1; row < n; row++) {
      if (Math.abs(aug[row][col]) > Math.abs(aug[maxRow][col])) maxRow = row;
    }
    [aug[col], aug[maxRow]] = [aug[maxRow], aug[col]];
    for (let row = col + 1; row < n; row++) {
      const f = aug[row][col] / aug[col][col];
      for (let j = col; j <= n; j++) aug[row][j] -= f * aug[col][j];
    }
  }
  const h = new Array(9).fill(0);
  h[8] = 1;
  for (let i = n - 1; i >= 0; i--) {
    h[i] = aug[i][n];
    for (let j = i + 1; j < n; j++) h[i] -= aug[i][j] * h[j];
    h[i] /= aug[i][i];
  }
  return h;
}

/**
 * Invert a 3×3 homography matrix using cofactor expansion.
 *
 * @param h - 9-element homography array
 * @returns 9-element inverse homography array
 */
export function inverseHomography(h: number[]): number[] {
  const m = [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], h[8]]];
  const det = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
              m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
              m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
  return [
    (m[1][1] * m[2][2] - m[1][2] * m[2][1]) / det,
    (m[0][2] * m[2][1] - m[0][1] * m[2][2]) / det,
    (m[0][1] * m[1][2] - m[0][2] * m[1][1]) / det,
    (m[1][2] * m[2][0] - m[1][0] * m[2][2]) / det,
    (m[0][0] * m[2][2] - m[0][2] * m[2][0]) / det,
    (m[0][2] * m[1][0] - m[0][0] * m[1][2]) / det,
    (m[1][0] * m[2][1] - m[1][1] * m[2][0]) / det,
    (m[0][1] * m[2][0] - m[0][0] * m[2][1]) / det,
    (m[0][0] * m[1][1] - m[0][1] * m[1][0]) / det
  ];
}

/**
 * Apply a homography transform to a single point.
 *
 * @param h - 9-element homography array
 * @param x - source x coordinate
 * @param y - source y coordinate
 * @returns transformed {x, y} point
 */
export function applyHomography(h: number[], x: number, y: number): Point {
  const w = h[6] * x + h[7] * y + h[8];
  return {
    x: (h[0] * x + h[1] * y + h[2]) / w,
    y: (h[3] * x + h[4] * y + h[5]) / w
  };
}

/**
 * Render artwork with perspective warp onto a 2000×2000 canvas.
 * Uses reverse-mapping with bilinear interpolation for quality.
 *
 * For each destination pixel in the bounding box of artworkCorners,
 * applies inverse homography to find the source pixel in the artwork,
 * then samples with bilinear interpolation.
 *
 * @param artwork - source artwork (ImageBitmap or HTMLCanvasElement)
 * @param artworkCorners - 4 destination corners [TL, TR, BR, BL] on the 2000×2000 canvas
 * @returns a 2000×2000 HTMLCanvasElement with the warped artwork
 */
export function drawPerspectiveArtwork(
  artwork: ImageBitmap | HTMLCanvasElement,
  artworkCorners: Point[]
): HTMLCanvasElement {
  const corners = artworkCorners;
  const minX = Math.max(0, Math.floor(Math.min(...corners.map(c => c.x))) - 5);
  const maxX = Math.min(2000, Math.ceil(Math.max(...corners.map(c => c.x))) + 5);
  const minY = Math.max(0, Math.floor(Math.min(...corners.map(c => c.y))) - 5);
  const maxY = Math.min(2000, Math.ceil(Math.max(...corners.map(c => c.y))) + 5);

  const artWidth = artwork.width;
  const artHeight = artwork.height;

  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = 2000;
  tempCanvas.height = 2000;
  const tempCtx = tempCanvas.getContext('2d')!;

  const srcCanvas = document.createElement('canvas');
  srcCanvas.width = artWidth;
  srcCanvas.height = artHeight;
  const srcCtx = srcCanvas.getContext('2d')!;
  srcCtx.drawImage(artwork, 0, 0);
  const srcData = srcCtx.getImageData(0, 0, artWidth, artHeight);

  // Map from normalised [0,1] square to destination corners
  const srcCorners: Point[] = [
    { x: 0, y: 0 }, { x: 1, y: 0 },
    { x: 1, y: 1 }, { x: 0, y: 1 }
  ];
  const h = computeHomography(srcCorners, corners);
  const hInv = inverseHomography(h);

  const destData = tempCtx.createImageData(2000, 2000);

  for (let y = minY; y < maxY; y++) {
    for (let x = minX; x < maxX; x++) {
      // Map destination pixel back to normalised source coordinates
      const norm = applyHomography(hInv, x, y);
      if (norm.x < 0 || norm.x > 1 || norm.y < 0 || norm.y > 1) continue;

      // Convert normalised coords to source pixel coords
      const srcX = norm.x * (artWidth - 1);
      const srcY = norm.y * (artHeight - 1);

      // Bilinear interpolation
      if (srcX >= 0 && srcX < artWidth - 1 && srcY >= 0 && srcY < artHeight - 1) {
        const x0 = Math.floor(srcX), y0 = Math.floor(srcY);
        const x1 = x0 + 1, y1 = y0 + 1;
        const xf = srcX - x0, yf = srcY - y0;

        const i00 = (y0 * artWidth + x0) * 4;
        const i01 = (y0 * artWidth + x1) * 4;
        const i10 = (y1 * artWidth + x0) * 4;
        const i11 = (y1 * artWidth + x1) * 4;
        const di = (y * 2000 + x) * 4;

        for (let c = 0; c < 4; c++) {
          const v = srcData.data[i00 + c] * (1 - xf) * (1 - yf) +
                    srcData.data[i01 + c] * xf * (1 - yf) +
                    srcData.data[i10 + c] * (1 - xf) * yf +
                    srcData.data[i11 + c] * xf * yf;
          destData.data[di + c] = Math.round(v);
        }
      }
    }
  }

  tempCtx.putImageData(destData, 0, 0);
  return tempCanvas;
}

/**
 * Extract a binary mask from a mask PNG's alpha channel.
 * Pixels with alpha > 10 are considered "inside" the mask.
 *
 * @param maskImg - an HTMLImageElement of the mask PNG
 * @returns MaskData with binary mask array, width, and height
 */
export function extractPanelMask(maskImg: HTMLImageElement): MaskData {
  const w = maskImg.width;
  const h = maskImg.height;
  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = w;
  tempCanvas.height = h;
  const tempCtx = tempCanvas.getContext('2d')!;
  tempCtx.drawImage(maskImg, 0, 0);
  const imageData = tempCtx.getImageData(0, 0, w, h);
  const data = imageData.data;
  const mask = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    mask[i] = data[i * 4 + 3] > 10 ? 1 : 0;
  }
  return { mask, width: w, height: h };
}

/**
 * Find the 4 corner points of a mask shape.
 * Used as a FALLBACK when no PIM coordinates are provided.
 * Finds the most extreme points in each quadrant relative to the mask's centroid.
 *
 * @param maskData - binary mask from extractPanelMask()
 * @returns 4 corner points [TL, TR, BR, BL]
 */
export function findPanelCorners(maskData: MaskData): Point[] {
  const { mask, width, height } = maskData;
  const edgePoints: Array<Point & { side: string }> = [];

  for (let y = 0; y < height; y++) {
    let leftX = -1, rightX = -1;
    for (let x = 0; x < width; x++) {
      if (mask[y * width + x]) { leftX = x; break; }
    }
    for (let x = width - 1; x >= 0; x--) {
      if (mask[y * width + x]) { rightX = x; break; }
    }
    if (leftX >= 0) edgePoints.push({ x: leftX, y, side: 'left' });
    if (rightX >= 0 && rightX !== leftX) edgePoints.push({ x: rightX, y, side: 'right' });
  }

  if (edgePoints.length < 4) {
    let minX = width, maxX = 0, minY = height, maxY = 0;
    for (const p of edgePoints) {
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
    return [
      { x: minX, y: minY }, { x: maxX, y: minY },
      { x: maxX, y: maxY }, { x: minX, y: maxY }
    ];
  }

  const cx = edgePoints.reduce((s, p) => s + p.x, 0) / edgePoints.length;
  const cy = edgePoints.reduce((s, p) => s + p.y, 0) / edgePoints.length;

  let topLeft: Point | null = null, topRight: Point | null = null;
  let bottomLeft: Point | null = null, bottomRight: Point | null = null;
  let tlDist = 0, trDist = 0, blDist = 0, brDist = 0;

  for (const p of edgePoints) {
    const dx = p.x - cx;
    const dy = p.y - cy;

    if (dx <= 0 && dy <= 0) {
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > tlDist) { tlDist = dist; topLeft = p; }
    }
    if (dx >= 0 && dy <= 0) {
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > trDist) { trDist = dist; topRight = p; }
    }
    if (dx >= 0 && dy >= 0) {
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > brDist) { brDist = dist; bottomRight = p; }
    }
    if (dx <= 0 && dy >= 0) {
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > blDist) { blDist = dist; bottomLeft = p; }
    }
  }

  const fallback = edgePoints[0];
  return [
    topLeft || fallback,
    topRight || fallback,
    bottomRight || fallback,
    bottomLeft || fallback
  ];
}

/**
 * Create initial artwork corner positions as a centered, aspect-ratio-preserving
 * rectangle within the panel bounds. Used as FALLBACK when no config coordinates exist.
 *
 * @param panelCorners - 4 corner points defining the panel area
 * @param artworkWidth - width of the uploaded artwork in pixels
 * @param artworkHeight - height of the uploaded artwork in pixels
 * @returns 4 corner points [TL, TR, BR, BL] for the artwork placement
 */
export function initArtworkCorners(
  panelCorners: Point[],
  artworkWidth: number,
  artworkHeight: number
): Point[] {
  const minX = Math.min(...panelCorners.map(c => c.x));
  const maxX = Math.max(...panelCorners.map(c => c.x));
  const minY = Math.min(...panelCorners.map(c => c.y));
  const maxY = Math.max(...panelCorners.map(c => c.y));

  const panelWidth = maxX - minX;
  const panelHeight = maxY - minY;
  const panelCenterX = (minX + maxX) / 2;
  const panelCenterY = (minY + maxY) / 2;

  let rectWidth: number, rectHeight: number;
  const fitScale = 0.85;

  if (artworkWidth && artworkHeight) {
    const artAspect = artworkWidth / artworkHeight;
    if (artAspect > panelWidth / panelHeight) {
      rectWidth = panelWidth * fitScale;
      rectHeight = rectWidth / artAspect;
    } else {
      rectHeight = panelHeight * fitScale;
      rectWidth = rectHeight * artAspect;
    }
  } else {
    rectWidth = panelWidth * fitScale;
    rectHeight = panelHeight * fitScale;
  }

  const left = panelCenterX - rectWidth / 2;
  const right = panelCenterX + rectWidth / 2;
  const top = panelCenterY - rectHeight / 2;
  const bottom = panelCenterY + rectHeight / 2;

  return [
    { x: left, y: top }, { x: right, y: top },
    { x: right, y: bottom }, { x: left, y: bottom }
  ];
}
```

---

## 7. React Component Architecture

### File Structure

```
src/components/product/
  BrandReadyButton.tsx              — Button + lazy-loaded modal
  brandready/
    BrandReadyModal.tsx             — 'use client' main modal overlay
    perspective.ts                  — Pure math functions (Section 6 above)
    useBrandReadyEngine.ts          — Custom hook: canvas, image loading, render, drag
    ArtworkUploader.tsx             — Upload drop zone per area
```

### BrandReadyButton.tsx

```typescript
'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { Paintbrush } from 'lucide-react';
import type { BrandReadyData } from '@/types/product';

const BrandReadyModal = dynamic(
  () => import('./brandready/BrandReadyModal'),
  { ssr: false }
);

interface BrandReadyButtonProps {
  productName: string;
  orderCodeSlug: string;
  brandready: BrandReadyData;
}

export default function BrandReadyButton({
  productName,
  orderCodeSlug,
  brandready
}: BrandReadyButtonProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-white font-body
                   rounded-lg hover:bg-primary-dark transition-colors text-sm font-medium"
      >
        <Paintbrush className="w-4 h-4" />
        BrandReady — Visualise Your Branding
      </button>

      {isOpen && (
        <BrandReadyModal
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
          productName={productName}
          orderCodeSlug={orderCodeSlug}
          brandready={brandready}
        />
      )}
    </>
  );
}
```

### BrandReadyModal.tsx — Key Behaviour

This is a `'use client'` component. Key details:

**Modal overlay pattern** (match existing site modals):
```typescript
// Fixed overlay with z-[100], body scroll lock, Escape key
useEffect(() => {
  document.body.style.overflow = 'hidden';
  const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
  window.addEventListener('keydown', handleEsc);
  return () => {
    document.body.style.overflow = '';
    window.removeEventListener('keydown', handleEsc);
  };
}, [onClose]);
```

**Layout:**
- Desktop (≥768px): `grid grid-cols-[320px_1fr]` — controls left, canvas right
- Mobile (<768px): single column — canvas on top, controls below

**Dynamic area initialisation:**
```typescript
// Determine which areas are active for this product
const activeAreas = Object.entries(brandready.coordinates)
  .filter(([areaKey, coords]) => {
    const hasCoords = coords.top_left.x !== null && coords.top_left.y !== null;
    const maskKey = `brandready_${areaKey}`;
    const hasMask = !!brandready.images[maskKey];
    return hasCoords && hasMask;
  })
  .map(([areaKey]) => areaKey);
```

**Converting PIM coordinates to engine format:**
```typescript
// PIM gives: { top_left: {x, y}, top_right: {x, y}, bottom_right: {x, y}, bottom_left: {x, y} }
// Engine expects: [TL, TR, BR, BL] as Point[]
function pimCoordsToCorners(coords: BrandReadyAreaCoords): Point[] {
  return [
    { x: Number(coords.top_left.x), y: Number(coords.top_left.y) },
    { x: Number(coords.top_right.x), y: Number(coords.top_right.y) },
    { x: Number(coords.bottom_right.x), y: Number(coords.bottom_right.y) },
    { x: Number(coords.bottom_left.x), y: Number(coords.bottom_left.y) },
  ];
}
```

### useBrandReadyEngine.ts — Custom Hook

This hook manages:

1. **Image loading** — load main image, overlay, and mask PNGs:
```typescript
// Load images from local synced paths (no CORS issues)
const basePath = `/products/${orderCodeSlug}/brandready`;
const mainImg = await loadImage(`${basePath}/main.png`);
const overlayImg = await loadImage(`${basePath}/overlay.png`);

// Load masks only for active areas
for (const areaKey of activeAreas) {
  const maskImg = await loadImage(`${basePath}/mask-${areaKey}.png`);
  // Store maskImg for destination-in compositing
}
```

2. **AVIF detection** — try AVIF for main image, fall back to PNG:
```typescript
async function supportsAvif(): Promise<boolean> {
  const img = new Image();
  return new Promise(resolve => {
    img.onload = () => resolve(img.width > 0);
    img.onerror = () => resolve(false);
    img.src = 'data:image/avif;base64,AAAAIGZ0eXBhdmlmAAAAAGF2aWZtaWYxbWlhZk1BMUIAAADybWV0YQAAAAAAAAAoaGRscgAAAAAAAAAAcGljdAAAAAAAAAAAAAAAAGxpYmF2aWYAAAAADnBpdG0AAAAAAAEAAAAeaWxvYwAAAABEAAABAAEAAAABAAABGgAAAB0AAAAoaWluZgAAAAAAAQAAABppbmZlAgAAAAABAABhdjAxQ29sb3IAAAAAamlwcnAAAABLaXBjbwAAABRpc3BlAAAAAAAAAAIAAAACAAAAEHBpeGkAAAAAAwgICAAAAAxhdjFDgQ0MAAAAABNjb2xybmNseAACAAIAAYAAAAAXaXBtYQAAAAAAAAABAAEEAQKDBAAAACVtZGF0EgAKCBgANogQEAwgMg8f8D///8WfhwB8+ErU42Y=';
  });
}

const useAvif = await supportsAvif();
const mainSrc = `${basePath}/main.${useAvif ? 'avif' : 'png'}`;
```

3. **The render pipeline** — this is the exact compositing order:

```typescript
function render() {
  if (!mainImage || !canvasRef.current) return;
  const ctx = canvasRef.current.getContext('2d')!;

  // Step 1: Clear and draw base product image
  ctx.clearRect(0, 0, 2000, 2000);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, 2000, 2000);
  ctx.drawImage(mainImage, 0, 0, 2000, 2000);

  // Step 2: For each active area with uploaded artwork
  for (const areaKey of activeAreas) {
    const areaState = areasRef.current[areaKey];
    if (!areaState?.artwork || !areaState?.artworkCorners) continue;

    // 2a: Perspective warp the artwork
    const artCanvas = drawPerspectiveArtwork(areaState.artwork, areaState.artworkCorners);

    // 2b: Pixel-perfect mask clipping using destination-in compositing
    const maskImg = areaState.maskImage;
    if (maskImg) {
      const maskCanvas = document.createElement('canvas');
      maskCanvas.width = 2000;
      maskCanvas.height = 2000;
      const maskCtx = maskCanvas.getContext('2d')!;

      // Draw the perspective-warped artwork
      maskCtx.drawImage(artCanvas, 0, 0);

      // Clip to mask alpha channel
      maskCtx.globalCompositeOperation = 'destination-in';
      maskCtx.drawImage(maskImg, 0, 0, 2000, 2000);

      // Draw the masked result onto the main canvas
      ctx.drawImage(maskCanvas, 0, 0);
    }
  }

  // Step 3: Draw overlay (shadows/highlights) on top
  if (overlayImage) {
    ctx.drawImage(overlayImage, 0, 0, 2000, 2000);
  }

  // Step 4: Draw corner handles (desktop only)
  if (showHandles && activeArea) {
    const area = areasRef.current[activeArea];
    if (area?.artworkCorners) {
      drawArtworkBoundary(ctx, area.artworkCorners, AREA_COLORS[activeArea]);
      area.artworkCorners.forEach((corner, i) => {
        drawHandle(ctx, corner.x, corner.y, AREA_COLORS[activeArea], isDragging && dragCornerIndex === i);
      });
    }
  }
}
```

4. **File upload handling:**

```typescript
async function handleFileUpload(file: File, areaKey: string) {
  // Validate
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
  const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'application/pdf'];
  if (!ALLOWED_TYPES.includes(file.type)) { setError('Please upload a PNG, JPEG, or PDF'); return; }
  if (file.size > MAX_FILE_SIZE) { setError('File must be under 10MB'); return; }

  let imageData: ImageBitmap | HTMLCanvasElement;

  if (file.type === 'application/pdf') {
    // Dynamic import of pdf.js
    const pdfjsLib = await import('pdfjs-dist');
    pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    const page = await pdf.getPage(1);
    const scale = 2;
    const viewport = page.getViewport({ scale });
    const pdfCanvas = document.createElement('canvas');
    pdfCanvas.width = viewport.width;
    pdfCanvas.height = viewport.height;
    await page.render({ canvasContext: pdfCanvas.getContext('2d')!, viewport }).promise;
    imageData = pdfCanvas;
  } else {
    imageData = await createImageBitmap(file);
  }

  const area = areasRef.current[areaKey];
  area.artwork = imageData;
  area.filename = file.name;

  // If PIM coordinates exist, map artwork directly to those corners
  if (area.configCorners) {
    area.artworkCorners = area.configCorners.map(c => ({ ...c }));
  } else {
    // Fallback: centered rectangle within the panel bounds
    area.artworkCorners = initArtworkCorners(area.panelCorners, imageData.width, imageData.height);
  }

  render();
}
```

5. **Download:**

```typescript
function downloadPreview() {
  // Temporarily hide handles
  const prevShowHandles = showHandles;
  setShowHandles(false);
  render();

  const link = document.createElement('a');
  link.download = `${orderCodeSlug}-branded.png`;
  link.href = canvasRef.current!.toDataURL('image/png');
  link.click();

  setShowHandles(prevShowHandles);
  render();
}
```

6. **Mouse drag for corner handles (desktop only):**

```typescript
function getCanvasCoords(e: MouseEvent): Point {
  const rect = canvasRef.current!.getBoundingClientRect();
  const scaleX = 2000 / rect.width;
  const scaleY = 2000 / rect.height;
  return {
    x: (e.clientX - rect.left) * scaleX,
    y: (e.clientY - rect.top) * scaleY
  };
}

// On mousedown: find if a handle is within hit radius, start drag
// On mousemove: update the dragged corner position, re-render
// On mouseup: stop dragging
```

---

## 8. Styling Specification

Map from the standalone dark theme to the Rhino website's light theme:

| Element | Tailwind Classes |
|---|---|
| Modal backdrop | `fixed inset-0 z-[100] bg-black/50 backdrop-blur-sm` |
| Modal content | `bg-white rounded-xl shadow-2xl max-w-7xl mx-auto my-4 max-h-[95vh] overflow-hidden` |
| Header bar | `bg-light-grey-bg px-6 py-4 border-b border-border-grey flex items-center justify-between` |
| Modal title | `font-heading text-xl text-near-black` |
| Close button | `text-dark-grey hover:text-near-black` (use `X` from lucide-react) |
| Controls panel | `bg-light-grey-bg p-6 overflow-y-auto` |
| Section headings | `font-heading text-sm font-semibold text-near-black uppercase tracking-wide mb-3` |
| Upload drop zone | `border-2 border-dashed border-border-grey rounded-lg p-6 text-center cursor-pointer hover:border-primary hover:bg-light-teal transition-colors` |
| Upload zone (dragover) | `border-primary bg-light-teal` |
| Primary button | `bg-primary text-white px-4 py-2 rounded-lg hover:bg-primary-dark font-body text-sm` |
| Secondary button | `border border-border-grey text-dark-grey px-4 py-2 rounded-lg hover:bg-light-grey-bg font-body text-sm` |
| Active panel tab | `border-primary text-primary bg-light-teal` |
| Inactive panel tab | `border-border-grey text-dark-grey hover:border-primary/50` |
| Canvas container | `bg-white rounded-lg shadow-inner p-2` |
| Error message | `text-red-600 text-sm mt-2` |
| Body text | `font-body text-dark-grey text-sm` |

**Icons** (from `lucide-react`):
- `Upload` — drop zone icon
- `X` — close button and clear artwork
- `Download` — download button
- `RotateCcw` — reset all button
- `Paintbrush` — BrandReady launch button
- `Eye` / `EyeOff` — toggle corner handles

---

## 9. Mobile Responsiveness

**Breakpoint:** `md` (768px)

| Aspect | Desktop (≥768px) | Mobile (<768px) |
|---|---|---|
| Layout | `grid grid-cols-[320px_1fr]` | Single column, canvas first |
| Corner handles | Visible, draggable | **Hidden** — not rendered |
| "Adjust Artwork" section | Visible (panel selector, handle toggles) | **Hidden entirely** |
| Artwork positioning | Auto-fit + drag to fine-tune | **Auto-fit only** |
| Upload drop zones | Standard size | Full-width, `min-h-[80px]` for touch |
| Download button | In controls panel | Sticky bottom or prominent placement |
| Canvas display | Fills remaining width | `width: 100%` of viewport |

**Implementation:**
- Use Tailwind responsive classes: `hidden md:block` for desktop-only elements
- Or use `useEffect` + `window.matchMedia('(min-width: 768px)')` for logic-dependent behaviour
- Canvas element should always render at 2000×2000 internally, but display at viewport width via CSS `width: 100%`

---

## 10. Product Detail Page Integration

**File:** `src/app/products/[category]/[modelSlug]/page.tsx`

### Placement

Add the BrandReady button **below the image gallery** in the left column. This keeps it contextually linked to the product visuals.

### Code

```typescript
import { hasBrandReady } from '@/lib/pim';
import BrandReadyButton from '@/components/product/BrandReadyButton';
import { toSlug } from '@/lib/utils';

// Inside the page component (this is a server component):
const showBrandReady = hasBrandReady(product);
const orderCodeSlug = toSlug(product.order_code);

// In the JSX, after ProductGallery in the left column:
{showBrandReady && product.brandready && (
  <div className="mt-6">
    <BrandReadyButton
      productName={product.model_name || ''}
      orderCodeSlug={orderCodeSlug}
      brandready={product.brandready}
    />
  </div>
)}
```

---

## Appendix A: Area Display Configuration

```typescript
export const AREA_COLORS: Record<string, string> = {
  front_panel: '#518BA0',   // primary teal
  lh_side: '#D4903C',       // accent amber
  rh_side: '#E67E22',       // warm orange
  light_canopy: '#F59E0B',  // amber
  door_glass: '#6366F1',    // indigo
};

export const AREA_LABELS: Record<string, string> = {
  front_panel: 'Front Panel',
  lh_side: 'Left Side',
  rh_side: 'Right Side',
  light_canopy: 'Light Canopy',
  door_glass: 'Door Glass',
};
```

---

## Appendix B: Testing Checklist

1. Product **with** BrandReady data in PIM shows the BrandReady button on its product page
2. Product **without** BrandReady data does NOT show the button
3. A product with only 2 areas (e.g. front + left side) shows exactly 2 upload zones
4. A product with 3 areas shows exactly 3 upload zones
5. BrandReady modal opens and displays the base product image correctly
6. Dropping PNG artwork auto-fits to the PIM-defined corners
7. Dropping JPEG artwork works
8. Dropping PDF artwork works (renders first page)
9. File over 10MB shows error message
10. Invalid file type shows error message
11. Corner handles are draggable for fine-tuning (desktop only)
12. Re-uploading artwork on the same area resets to the PIM-defined corners
13. "Clear" removes artwork from an area
14. Download produces a 2000×2000 PNG with branding applied (no handles visible)
15. Multiple areas can have different artwork simultaneously
16. Shared edges between adjacent panels (e.g. front and left side) produce a seamless join
17. Mobile: auto-fit only, no drag handles, usable touch targets
18. Overlay (shadows/highlights) renders on top of artwork
19. Mask alpha channel clips pixel-perfectly (no fringing at edges)
20. Modal closes on Escape key and on clicking outside the modal content
21. Body scroll is locked when modal is open, restored when closed
22. AVIF loads on supported browsers, PNG fallback on unsupported
23. Canvas renders at 2000×2000 internally regardless of displayed size

---

## Appendix C: CORS Note

The sync script downloads BrandReady images from the PIM and stores them locally in `public/products/`. This means the component loads images from the **same domain** as the website — no CORS issues. If you ever need to load images directly from PIM URLs at runtime instead, the PIM server would need to send `Access-Control-Allow-Origin` headers for the website domain.

---

## Appendix D: PIM Setup Guide

For each product you want to add BrandReady support to:

1. **Create images in Photoshop** (all 2000×2000px PNG):
   - Base product photo (clean, no branding)
   - One mask per branding area (white shape on transparent background)
   - Overlay with shadows/highlights

2. **Measure corner coordinates** (Photoshop Info panel, F8):
   - Hover over each corner of each branding panel
   - Record X,Y pixel coordinates
   - Order: Top-Left, Top-Right, Bottom-Right, Bottom-Left (clockwise)
   - Where two panels share an edge, coordinates must match exactly

3. **Upload to PIM** under the product's BrandReady section

4. **Run sync**: `npm run sync` on the website to download images and rebuild data
