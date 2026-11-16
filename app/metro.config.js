// Metro only bundles files inside the project by default; the app imports
// ../schema/books.json (shared with the pipeline), so watch that folder too.
const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);
config.watchFolders = [path.resolve(__dirname, "../schema")];
module.exports = config;
