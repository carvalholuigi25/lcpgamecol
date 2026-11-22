const path = require('node:path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// src/i18n imports the translations shared with the web pages from the repository's
// locales/ folder, which sits outside this project.
config.watchFolders = [...(config.watchFolders ?? []), path.resolve(__dirname, '..', 'locales')];

module.exports = config;
