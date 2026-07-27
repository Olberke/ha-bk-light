$ReadmePath = ".\README.md"
$Readme = Get-Content -LiteralPath $ReadmePath -Raw

if ($Readme -notmatch "Pupariaa/Bk-Light-AppBypass") {
@'

## Credits and attribution

This Home Assistant integration is based in part on protocol knowledge and
tooling from the BK-Light toolkit created by
[Puparia](https://github.com/Pupariaa).

Original project:

[Pupariaa/Bk-Light-AppBypass](https://github.com/Pupariaa/Bk-Light-AppBypass)

The original project is distributed under the MIT License.

Copyright (c) 2025 Puparia (Pupariaa)

If you reuse this toolkit or derivatives, credit
“Puparia / https://github.com/Pupariaa” and link back to the original
repository.
'@ | Add-Content -Encoding utf8 -LiteralPath $ReadmePath
}