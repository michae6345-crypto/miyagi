#!/usr/bin/env bash
# Pack vscode-ext/ into a .vsix with plain `zip` (no npm, no vsce), for `code --install-extension`.
#
#   scripts/package-vscode-ext.sh                  # -> vscode-ext/dist/miyagi-companion-<version>.vsix
#   scripts/package-vscode-ext.sh /tmp/out.vsix    # any output path
#
# A .vsix is a zip: [Content_Types].xml + extension.vsixmanifest + extension/<the extension's files>.
# Only package.json, extension.js and README.md go in (the tests stay out).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$ROOT/vscode-ext"
[ -f "$EXT/package.json" ] || { echo "[vsix] no $EXT/package.json" >&2; exit 1; }

# Read package.json without node or jq: plutil reads JSON on macOS; python3 elsewhere.
field() {
  if command -v plutil >/dev/null 2>&1; then
    plutil -extract "$1" raw -o - "$EXT/package.json" 2>/dev/null || true
  else
    python3 -c 'import json,sys; v=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): v=v.get(k,"") if isinstance(v,dict) else ""
print(v)' "$EXT/package.json" "$1" 2>/dev/null || true
  fi
}
xml() { sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g' -e 's/"/\&quot;/g'; }

NAME="$(field name)"; PUBLISHER="$(field publisher)"; VERSION="$(field version)"
DISPLAY="$(field displayName | xml)"; DESC="$(field description | xml)"; ENGINE="$(field engines.vscode)"
[ -n "$NAME" ] && [ -n "$PUBLISHER" ] && [ -n "$VERSION" ] || { echo "[vsix] package.json needs name, publisher, version" >&2; exit 1; }

OUT="${1:-$EXT/dist/$PUBLISHER-$NAME-$VERSION.vsix}"
case "$OUT" in /*) ;; *) OUT="$PWD/$OUT" ;; esac
mkdir -p "$(dirname "$OUT")"

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/miyagi-vsix.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/extension"
for f in package.json extension.js README.md; do
  [ -f "$EXT/$f" ] && cp "$EXT/$f" "$STAGE/extension/$f"
done

cat >"$STAGE/[Content_Types].xml" <<'EOF'
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension=".json" ContentType="application/json"/>
  <Default Extension=".js" ContentType="application/javascript"/>
  <Default Extension=".md" ContentType="text/markdown"/>
  <Default Extension=".vsixmanifest" ContentType="text/xml"/>
</Types>
EOF

cat >"$STAGE/extension.vsixmanifest" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">
  <Metadata>
    <Identity Language="en-US" Id="$NAME" Version="$VERSION" Publisher="$PUBLISHER"/>
    <DisplayName>$DISPLAY</DisplayName>
    <Description xml:space="preserve">$DESC</Description>
    <Categories>Other</Categories>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="$ENGINE"/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value=""/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value=""/>
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
  </Assets>
</PackageManifest>
EOF

rm -f "$OUT"
(cd "$STAGE" && zip -qrX "$OUT" "[Content_Types].xml" extension.vsixmanifest extension)
echo "$OUT"
