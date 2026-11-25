[![Express Logo](https://example.org/express.png)](https://expressjs.com/)

# Express

**Fast, unopinionated, minimalist web framework for [Node.js](https://nodejs.org).**

[![NPM Version][npm-version-image]][npm-url] [![NPM Downloads][npm-downloads-image]][npm-downloads-url]

## Installation

This is a Node.js module available through the npm registry. Before installing, download and install Node.js 18 or
higher. In a new folder, create a `package.json` with `npm init`, then install Express:

```bash
npm install express
```

## Quick Start

Create `app.js` with the smallest possible server:

```js
const express = require('express')
const app = express()

app.get('/', (req, res) => {
  res.send('Hello World')
})
```

Then start listening on a port, at the end of `app.js`:

```js
app.listen(3000, () => {
  console.log('Listening on port 3000')
})
```

Run it and open http://localhost:3000 in your browser:

```console
$ node app.js
Listening on port 3000
```

## Philosophy

The Express philosophy is to provide small, robust tooling for HTTP servers, making it a great solution for single
page applications, websites, hybrids, or public HTTP APIs. Express does not force you to use any specific ORM or
template engine.

## Features

  * Robust routing
  * Focus on high performance
  * Super-high test coverage
  * HTTP helpers (redirection, caching, etc)

## License

[MIT](LICENSE)

[npm-version-image]: https://badgen.net/npm/v/express
[npm-url]: https://npmjs.org/package/express
[npm-downloads-image]: https://badgen.net/npm/dm/express
[npm-downloads-url]: https://npmcharts.com/compare/express?minimal=true
