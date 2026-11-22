# Merge the per-arch latest-mac-<arch>.yml files that app/scripts/release-mac.sh writes into one latest-mac.yml, the
# electron-updater feed for the release (.github/workflows/release.yml, publish job). Ruby's YAML is in the standard
# library of every GitHub runner and every Mac, so this needs no npm install.
#
#   ruby .github/scripts/merge-mac-feed.rb latest-mac-arm64.yml latest-mac-x64.yml > latest-mac.yml
#
# Every input must be for the same version. `files` is every input's files in order; the legacy top-level path/sha512
# stay those of the first input (arm64 first: electron-updater picks per arch from `files`, by "arm64" in the name).
require 'yaml'

abort 'usage: merge-mac-feed.rb latest-mac-<arch>.yml...' if ARGV.empty?
feeds = ARGV.map do |f|
  doc = YAML.safe_load(File.read(f), permitted_classes: [], aliases: false)
  abort "#{f}: not an electron-builder feed (no version or files)" unless doc.is_a?(Hash) && doc['version'] && doc['files'].is_a?(Array)
  doc
end
versions = feeds.map { |d| d['version'].to_s }.uniq
abort "feeds disagree on the version: #{versions.join(', ')}" if versions.size != 1

merged = feeds.first.dup
merged['files'] = feeds.flat_map { |d| d['files'] }
urls = merged['files'].map { |f| f['url'] }
abort "the same file twice: #{urls.join(', ')}" if urls.uniq.size != urls.size
releases = feeds.map { |d| d['releaseDate'].to_s }.reject(&:empty?)
merged['releaseDate'] = releases.max unless releases.empty?
print YAML.dump(merged)
