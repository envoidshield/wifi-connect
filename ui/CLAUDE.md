# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in the UI directory.

## UI Overview

WiFi Connect UI is a React-based captive portal interface built with TypeScript and the Rendition component library (Balena's UI framework). It provides a user-friendly interface for connecting Linux devices to WiFi networks.

## Development Commands

```bash
# Install dependencies
npm install

# Start development server (runs on localhost:3000)
npm start

# Build production bundle
npm run build

# Lint the code
npm run lint

# Run tests
npm test
```

## Architecture

### Technology Stack
- **React 16.13** with TypeScript
- **Rendition 35.2.0**: Balena's component library providing styled UI components
- **styled-components 5.0**: CSS-in-JS for component styling
- **create-react-app**: Build tooling (using react-scripts 5.0.1)

### Component Structure

1. **App.tsx**: Main application component
   - Manages global state (network fetching, connection attempts, errors)
   - Fetches available networks from `/networks` endpoint on mount
   - Handles connection requests via POST to `/connect`
   - Provides Rendition theme context via Provider

2. **NetworkInfoForm.tsx**: Network selection and credential input form
   - Dynamically generates JSON Schema based on available networks
   - Supports both standard WPA/WPA2 and enterprise networks
   - Shows/hides identity field based on network security type
   - Uses Rendition's Form component with JSON Schema validation

3. **Notifications.tsx**: User feedback component
   - Displays connection status messages
   - Shows error messages when connection fails
   - Provides success feedback after connection attempts

### API Endpoints

The UI communicates with the Rust backend via two endpoints:

- **GET /networks**: Returns array of available networks
  ```typescript
  interface Network {
    ssid: string;
    security: string; // "open", "wpa", "enterprise"
  }
  ```

- **POST /connect**: Submits connection credentials
  ```typescript
  interface NetworkInfo {
    ssid?: string;
    identity?: string;    // For enterprise networks
    passphrase?: string;
  }
  ```

### Styling Approach

- Global styles via styled-components' `createGlobalStyle`
- Component-specific styles using styled-components
- Rendition theme provides consistent design system
- Custom navbar branding with logo and text

### Build Configuration

- TypeScript strict mode enabled
- ES5 target for browser compatibility
- Source maps disabled in production builds
- Polyfills included for fetch API and Promises for older browsers

## Important Considerations

- The UI expects to be served from the root path by the Rust server
- Development proxy is not configured - direct API calls to relative paths
- The build output in `build/` directory is served statically by the main application
- All network requests use the fetch API with polyfills for compatibility
- Enterprise network support requires the identity field for 802.1X authentication
- The UI is designed to work in captive portal scenarios where internet access is limited