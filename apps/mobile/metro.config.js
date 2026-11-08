const { getDefaultConfig } = require("expo/metro-config");
const fs = require("fs");
const path = require("path");

const config = getDefaultConfig(__dirname);

// @ai-pos/shared-types is TypeScript source. Its relative imports use the .js
// specifier TypeScript emits. Metro must follow those to the .ts files.
const sharedTypesRoot = path.resolve(__dirname, "../../packages/shared-types");
config.resolver.resolveRequest = (context, moduleName, platform) => {
  const origin = context.originModulePath;
  if (
    origin &&
    origin.startsWith(sharedTypesRoot) &&
    moduleName.startsWith(".") &&
    moduleName.endsWith(".js")
  ) {
    const candidate = path.resolve(path.dirname(origin), moduleName.slice(0, -3) + ".ts");
    if (fs.existsSync(candidate)) {
      return { type: "sourceFile", filePath: candidate };
    }
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
