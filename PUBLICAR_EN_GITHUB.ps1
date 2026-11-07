# Publica los archivos del ZIP en una rama nueva y abre una Pull Request.
# Requiere Git y GitHub CLI (`gh`) autenticados con permisos de escritura.
$ErrorActionPreference = 'Stop'
$repo = 'ipeidro-source/youtube-smart-downloader'
$branch = 'feature/desktop-app-v0.1'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($tool in @('git', 'gh')) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    throw "Falta $tool. Instálalo e inicia sesión con 'gh auth login' antes de continuar."
  }
}
gh auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI no está autenticado. Ejecuta gh auth login.' }
$target = Join-Path $env:TEMP ('YouTubeSmartDownloader-publish-' + [guid]::NewGuid().ToString('N'))
git clone "https://github.com/$repo.git" "$target"
if ($LASTEXITCODE -ne 0) { throw 'No se ha podido clonar el repositorio.' }
Push-Location $target
try {
  git switch -c $branch
  if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la rama.' }
  $exclude = @('.git', '.pytest_cache', '__pycache__', '.venv')
  foreach ($item in (Get-ChildItem -LiteralPath $root -Force)) {
    if ($item.Name -notin $exclude -and $item.Name -ne 'PUBLICAR_EN_GITHUB.ps1') {
      Copy-Item -LiteralPath $item.FullName -Destination $target -Recurse -Force
    }
  }
  git add .
  git commit -m 'feat: add Windows GUI, audio-language policy, tests and CI'
  if ($LASTEXITCODE -ne 0) { throw 'No se ha creado el commit.' }
  git push -u origin $branch
  if ($LASTEXITCODE -ne 0) { throw 'GitHub ha rechazado el push. Comprueba los permisos.' }
  gh pr create --repo $repo --base main --head $branch --title 'feat: Windows GUI downloader v0.1' --body 'Adds CustomTkinter GUI, strict audio language selection, resumable playlists, dependency setup, tests, documentation and Windows CI/release workflows.'
  if ($LASTEXITCODE -ne 0) { Write-Warning 'La rama se ha publicado, pero no se ha podido abrir la PR.' }
} finally {
  Pop-Location
}
