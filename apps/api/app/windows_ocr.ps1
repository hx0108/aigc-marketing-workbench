param([Parameter(Mandatory=$true)][string]$Manifest)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
$null=[Windows.Globalization.Language,Windows.Globalization,ContentType=WindowsRuntime]
$asTask=([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {$_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1})[0]
function Wait-WinRT($Operation,$ResultType){
    $task=$asTask.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
    $task.Wait() | Out-Null
    return $task.Result
}
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('zh-Hans-CN'))
if($null -eq $engine){throw 'LOCAL_OCR_LANGUAGE_UNAVAILABLE'}
$inputs=Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$outputs=@()
foreach($inputItem in $inputs){
    $file=Wait-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($inputItem.path)) ([Windows.Storage.StorageFile])
    $stream=Wait-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder=Wait-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap=Wait-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $result=Wait-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $lines=@()
            foreach($line in $result.Lines){
                $words=@()
                foreach($word in $line.Words){$r=$word.BoundingRect;$words+=@{text=$word.Text;region=@{x=$r.X;y=$r.Y;width=$r.Width;height=$r.Height}}}
                $lines+=@{text=$line.Text;words=$words}
            }
            $outputs+=@{page=$inputItem.page;text=$result.Text;lines=$lines;engine='windows_ocr';confidence=$null;requires_review=$true}
        } finally {$bitmap.Dispose()}
    } finally {$stream.Dispose()}
}
ConvertTo-Json -InputObject @($outputs) -Depth 10 -Compress
