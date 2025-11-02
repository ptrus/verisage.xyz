# Verisage Frontend

Frontend for Verisage Oracle - deployed to Cloudflare Pages.

## Local Development

```bash
# From project root
make dev-frontend

# Or directly from frontend-src/
npm install
npm run dev
```

The dev server will start on `http://localhost:5173` and proxy API requests to `http://localhost:8000` by default.

## Deployment to Cloudflare Pages

### Initial Setup

1. Install Wrangler CLI:

   ```bash
   npm install -g wrangler
   ```

2. Login to Cloudflare:

   ```bash
   wrangler login
   ```

3. Create the Pages project:
   ```bash
   cd frontend-src
   wrangler pages project create verisage
   ```

### Deploy

#### Testnet/Preview Deployment

```bash
cd frontend-src
VITE_API_URL=https://testnet-api.verisage.xyz npm run build
wrangler pages deploy dist --project-name=verisage --branch=preview
```

#### Production Deployment

```bash
cd frontend-src
VITE_API_URL=https://api.verisage.xyz npm run build
wrangler pages deploy dist --project-name=verisage --branch=main
```

### Environment Variables

Set in Cloudflare Pages dashboard under Settings > Environment variables:

- `VITE_API_URL` - API endpoint URL (e.g., `https://testnet-api.verisage.xyz`)

### CI/CD with GitHub Actions

Cloudflare Pages automatically deploys from GitHub when connected. Configure build settings:

- **Build command**: `npm run build`
- **Build output directory**: `dist`
- **Root directory**: `frontend-src`
- **Environment variables**: Set `VITE_API_URL` for production and preview branches
