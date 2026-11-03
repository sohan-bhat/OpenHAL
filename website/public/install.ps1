function Install-OpenHAL {
  $Distribution = 'halkit'
  $Repository = 'https://github.com/sohan-bhat/OpenHAL'
  $UvVersion = '0.13.5'
  $PythonVersion = '3.12'

  $ErrorActionPreference = 'Stop'
  $ProgressPreference = 'SilentlyContinue'
  if ($PSVersionTable.PSVersion.Major -lt 6) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
  }

  function Test-Address([string]$Address) {
    try {
      Invoke-WebRequest -Uri $Address -Method Head -UseBasicParsing | Out-Null
      return $true
    } catch {
      $response = $_.Exception.Response
      if ($null -ne $response -and [int]$response.StatusCode -eq 404) {
        return $false
      }
      throw "The installer could not reach $Address. Check the network connection, then run the installer again."
    }
  }

  $uvDir = if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR } elseif ($env:XDG_BIN_HOME) { $env:XDG_BIN_HOME } else { Join-Path $HOME '.local\bin' }
  $uv = $null
  $onPath = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($onPath) {
    $uv = $onPath.Source
  } elseif (Test-Path (Join-Path $uvDir 'uv.exe')) {
    $uv = Join-Path $uvDir 'uv.exe'
  } else {
    Write-Host "Installing uv $UvVersion in $uvDir"
    $shell = (Get-Process -Id $PID).Path
    $saved = @($env:UV_INSTALL_DIR, $env:UV_NO_MODIFY_PATH)
    $env:UV_INSTALL_DIR = $uvDir
    $env:UV_NO_MODIFY_PATH = '1'
    try {
      & $shell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/$UvVersion/install.ps1 | iex"
      $code = $LASTEXITCODE
    } finally {
      $env:UV_INSTALL_DIR = $saved[0]
      $env:UV_NO_MODIFY_PATH = $saved[1]
    }
    $uv = Join-Path $uvDir 'uv.exe'
    if ($code -ne 0 -or -not (Test-Path $uv)) {
      throw 'The uv installer from astral.sh stopped with an error, so uv and OpenHAL are not installed.'
    }
  }

  $bin = (& $uv tool dir --bin | Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or -not $bin) {
    throw "The uv at $uv has no tool command. Update that uv, or remove it so the installer puts uv $UvVersion in place."
  }

  $version = "$env:OPENHAL_VERSION".TrimStart('v')
  $source = "$env:OPENHAL_SOURCE"
  if ($source) {
    $spec = if ($source -match '://') { "$Distribution @ $source" } else { $source }
    $where = $source
  } elseif ($version) {
    if (Test-Address "https://pypi.org/pypi/$Distribution/$version/json") {
      $spec = "$Distribution==$version"
      $where = 'PyPI'
    } elseif (Test-Address "$Repository/archive/refs/tags/v$version.tar.gz") {
      $spec = "$Distribution @ $Repository/archive/refs/tags/v$version.tar.gz"
      $where = "the tag v$version of $Repository"
    } else {
      throw "OpenHAL $version is neither on PyPI nor tagged v$version in $Repository. Leave OPENHAL_VERSION unset to install the newest OpenHAL."
    }
  } elseif (Test-Address "https://pypi.org/pypi/$Distribution/json") {
    $spec = $Distribution
    $where = 'PyPI'
  } else {
    $spec = "$Distribution @ $Repository/archive/refs/heads/main.tar.gz"
    $where = "the main branch of $Repository"
  }

  $wheels = @('--no-build')
  if (-not ($spec -eq $Distribution -or $spec.StartsWith("$Distribution==") -or $spec.EndsWith('.whl'))) {
    $wheels += @('--no-binary-package', $Distribution)
  }

  Write-Host "Installing OpenHAL from $where"
  $path = $env:Path
  $env:Path = "$bin;$env:Path"
  try {
    & $uv tool install --upgrade --compile-bytecode --python $PythonVersion @wheels $spec
    $code = $LASTEXITCODE
  } finally {
    $env:Path = $path
  }
  if ($code -ne 0) {
    throw 'uv stopped with the error above, so OpenHAL is not installed.'
  }

  $openhal = Join-Path $bin 'openhal.exe'
  $printed = (& $openhal --version | Out-String).Trim()
  if (-not $printed) {
    throw "uv finished, but $openhal --version printed nothing."
  }

  Write-Host ''
  Write-Host "OpenHAL $($printed -replace '^openhal\s+', '') is now in $bin."
  $folders = @($env:Path -split ';' | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') })
  if ($folders -contains $bin.TrimEnd('\')) {
    $other = Get-Command openhal -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($other -and $other.Source -ne $openhal) {
      Write-Host "PowerShell runs the openhal at $($other.Source), because that folder comes before $bin on your PATH."
    }
  } else {
    Write-Host ''
    Write-Host "$bin is not on your PATH yet. Add the folder for this window with"
    Write-Host "  `$env:Path = `"$bin;`$env:Path`""
    Write-Host 'and for every new window with'
    Write-Host "  & `"$uv`" tool update-shell"
  }
  Write-Host ''
  Write-Host 'Set up your first device and your AI clients with'
  Write-Host '  openhal init'
}

try {
  Install-OpenHAL
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  $global:LASTEXITCODE = 1
}
