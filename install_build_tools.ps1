Write-Host "Downloading Microsoft C++ Build Tools..."
Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vs_buildtools.exe" -OutFile "vs_buildtools.exe"

Write-Host "Installing Microsoft C++ Build Tools (this will take several minutes and download a few GBs)..."
$arguments = "--quiet --wait --norestart --nocache --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
Start-Process -FilePath ".\vs_buildtools.exe" -ArgumentList $arguments -Wait -NoNewWindow

Write-Host "Installation process finished."
