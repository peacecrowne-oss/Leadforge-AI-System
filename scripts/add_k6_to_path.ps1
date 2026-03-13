$k6Path = "C:\k6"

$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")

if ($currentPath -notlike "*$k6Path*") {
    $newPath = "$currentPath;$k6Path"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Host "k6 path added successfully."
} else {
    Write-Host "k6 path already exists."
}
