# MU300 network speed test for LuCI

This optional package adds **SpeedTest** under **Services** in LuCI. The browser sends synthetic test traffic to the selected public node only after the user starts a test. The traffic uses the internet connection and the node sees the browser's source address and origin. The browser performs the measurements and stores the results locally. Guangdong Mobile is the default node. The optional Clouvider Los Angeles node measures the route to the United States. The LuCI view and page resources use release-specific URLs so browsers fetch the installed revision after an upgrade.

## Build

Copy this directory to `package/luci-app-mu300-speedtest` in an OpenWrt SDK with the LuCI feed available. Select `luci-app-mu300-speedtest` in the SDK configuration, then compile the package.

```sh
make package/luci-app-mu300-speedtest/compile V=s
```

The package uses the SDK's `luci-base/host` dependency to build the Simplified Chinese catalog. All web resources are included in the source directory.

## LibreSpeed sources and licenses

The page uses Federico Dossena's LibreSpeed engine under LGPL v3. The vendored files originate from LibreSpeed Go v1.1.5. The LGPL v3 text and its accompanying GPL v3 text are included next to the JavaScript files as `LICENSE` and `COPYING`. [Release source](https://github.com/librespeed/speedtest-go/tree/v1.1.5/web/assets)

- `speedtest.js` is unchanged. Its SHA-256 is `55cfa1af1c421f9a0e1544c9975732f79b67eccc155d8443baaf9b2f1ee5bcd0`.
- The upstream `speedtest_worker.js` SHA-256 is `34bfb6c2a96886307d885193f53d035404780a0bf9a949ac5f18857ff2d0fe6b`. The two upload branches omit `Content-Encoding: identity` only for `https://www.speedtest.hk/speedtest/upload.php` because that node's CORS policy does not allow the header.
- The bundled worker SHA-256 is `58244812791d4995d2edc9dc6fb25f51cd16b9e49354094d6a15a84b3eef1ac9`.

First-party package code follows the project MIT license.
