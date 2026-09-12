param(
  [string]$RepoName = "shop-titans-bis-tracker"
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# Requisitos
# ----------------------------------------------------------------------

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "No se encuentra git en PATH. Instala Git antes de continuar."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "No se encuentra GitHub CLI (gh) en PATH. Instálalo y ejecuta: gh auth login"
}

gh auth status
if ($LASTEXITCODE -ne 0) {
  throw "GitHub CLI no está autenticado. Ejecuta: gh auth login"
}

# ----------------------------------------------------------------------
# Inicializar Git
# ----------------------------------------------------------------------

if (-not (Test-Path ".git")) {
  Write-Host "Inicializando repositorio Git..."
  
  git init
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudo inicializar el repositorio Git."
  }
}

# ----------------------------------------------------------------------
# Comprobar identidad Git
# ----------------------------------------------------------------------

$gitUserName = git config user.name
$gitUserEmail = git config user.email

if (-not $gitUserName -or -not $gitUserEmail) {
  throw "Git no tiene configurada la identidad del autor."
}

Write-Host ""
Write-Host "Identidad Git:"
Write-Host "  Nombre: $gitUserName"
Write-Host "  Email : $gitUserEmail"
Write-Host ""

# ----------------------------------------------------------------------
# Crear commit inicial si todavía no existe
# ----------------------------------------------------------------------

$hasCommit = $false

try {
  $commit = git rev-list -1 HEAD 2>$null
  $hasCommit = ($LASTEXITCODE -eq 0 -and $commit)
}
catch {
  $hasCommit = $false
}

if (-not $hasCommit) {
  Write-Host "Creando commit inicial..."

  git add .
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron añadir los archivos al repositorio Git."
  }

  git commit -m "Initial Shop Titans BiS tracker"
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudo crear el commit inicial."
  }
}

# Garantizar que la rama principal se llama main.
git branch -M main
if ($LASTEXITCODE -ne 0) {
  throw "No se pudo establecer la rama principal 'main'."
}

# ----------------------------------------------------------------------
# Usuario GitHub
# ----------------------------------------------------------------------

$owner = (gh api user --jq .login).Trim()
if (-not $owner) {
  throw "No se pudo obtener el usuario autenticado de GitHub."
}

Write-Host "Usuario GitHub: $owner"

# ----------------------------------------------------------------------
# Crear repositorio remoto o hacer push
# ----------------------------------------------------------------------

$remoteExists = git remote | Select-String -SimpleMatch "origin"

if (-not $remoteExists) {
  Write-Host ""
  Write-Host "Creando repositorio GitHub $owner/$RepoName..."
  
  gh repo create $RepoName `
    --public `
    --source=. `
    --remote=origin `
    --push
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudo crear el repositorio GitHub."
  }
} else {
  Write-Host ""
  Write-Host "El remoto origin ya existe. Realizando push..."
  
  git push -u origin main
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudo realizar el push a GitHub."
  }
}

# ----------------------------------------------------------------------
# GitHub Pages
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "Configurando GitHub Pages..."

gh api `
  --method POST `
  "repos/$owner/$RepoName/pages" `
  -f build_type=workflow `
  *> $null

if ($LASTEXITCODE -eq 0) {
  Write-Host "GitHub Pages activado en modo workflow."
}
else {
  Write-Host "Pages ya estaba activo o GitHub no permitió activarlo por API."
  Write-Host "Comprueba Settings > Pages > Source = GitHub Actions si fuera necesario."
}

# ----------------------------------------------------------------------
# Resultado
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "Repositorio: https://github.com/$owner/$RepoName"
Write-Host "Página pública (cuando termine el deploy): https://$owner.github.io/$RepoName/"