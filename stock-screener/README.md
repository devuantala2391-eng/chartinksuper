# Stock Screener - Angular Frontend

An Angular application for screening stocks based on technical indicators using configurable conditions.

## Features

- **Dynamic Condition Builder**: Add multiple conditions with AND/OR logic
- **Multiple Indicators Support**:
  - Daily/Weekly RSI, SMA, EMA
  - Bollinger Bands (Upper/Lower)
  - Supertrend
  - Price fields (Open, High, Low, Close, Volume)
  - Percent change
- **Results Grouping**: Results are grouped by date for easy analysis
- **Real-time Query Generation**: See the query being built as you add conditions
- **Responsive Design**: Works on desktop and mobile devices

## Prerequisites

- Node.js (v18 or higher)
- Angular CLI (v19)
- Backend server running on http://localhost:3000

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Karma](https://karma-runner.github.io) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
