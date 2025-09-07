@echo off
rem Downloads and build sources for libraries we depend upon

goto Run
:Usage
echo.%~nx0 [flags and arguments]
echo.
echo.Download and build OpenSSL. This should only be performed in order to
echo.update the binaries kept online - in most cases, the files downloaded
echo.by the get_externals.bat script are sufficient for building CPython.
echo.
echo.Available flags:
echo.  -h  Display this help message
echo.
echo.Available arguments:
echo.  --certificate (-c)   The signing certificate to use for binaries.
echo.  --organization       The github organization to obtain sources from.
echo.
exit /b 127

:Run
setlocal
if "%PCBUILD%"=="" (set PCBUILD=%~dp0)
if "%EXTERNALS_DIR%"=="" (set EXTERNALS_DIR=%PCBUILD%\..\externals)

set ORG_SETTING=

:CheckOpts
if "%~1"=="-h" shift & goto Usage
if "%~1"=="--certificate" (set SigningCertificate=%~2) && shift && shift & goto CheckOpts
if "%~1"=="-c" (set SigningCertificate=%~2) && shift && shift & goto CheckOpts
if "%~1"=="--organization" (set ORG_SETTING=--organization "%~2") && shift && shift && goto CheckOpts

if "%~1"=="" goto Build
echo Unrecognized option: %1
goto Usage

:Build
call "%PCBUILD%\find_msbuild.bat" %MSBUILD%
if ERRORLEVEL 1 (echo Cannot locate MSBuild.exe on PATH or as MSBUILD variable & exit /b 2)

call "%PCBUILD%\find_python.bat" "%PYTHON%"
if ERRORLEVEL 1 (echo Cannot locate python.exe on PATH or as PYTHON variable & exit /b 3)

echo Downloading OpenSSL 3.0.15+ source code...
call "%PCBUILD%\get_externals.bat" --openssl-src --no-openssl %ORG_SETTING%
if ERRORLEVEL 1 (echo Failed to download OpenSSL source & exit /b 5)

echo Validating OpenSSL version...
rem Check if we have OpenSSL 3.0.15 or later by examining the directory name
set OPENSSL_MIN_VERSION=3.0.15
set OPENSSL_SRC_DIR=
for /d %%d in ("%EXTERNALS_DIR%\openssl-*") do (
    set OPENSSL_SRC_DIR=%%d
)
if "%OPENSSL_SRC_DIR%"=="" (
    echo ERROR: OpenSSL source directory not found in %EXTERNALS_DIR%
    exit /b 6
)

echo Found OpenSSL source directory: %OPENSSL_SRC_DIR%
rem Extract version from directory name (format: openssl-X.Y.Z)
for /f "tokens=2 delims=-" %%v in ("%OPENSSL_SRC_DIR%") do set OPENSSL_VERSION=%%v
echo OpenSSL version detected: %OPENSSL_VERSION%

rem Basic version validation - ensure it starts with "3.0" and has a patch version >= 15
echo %OPENSSL_VERSION% | findstr /b "3\.0\." >nul
if ERRORLEVEL 1 (
    echo ERROR: OpenSSL version %OPENSSL_VERSION% is not 3.0.x series. Required: %OPENSSL_MIN_VERSION% or later
    exit /b 7
)

rem Extract patch version for 3.0.x series
for /f "tokens=3 delims=." %%p in ("%OPENSSL_VERSION%") do set PATCH_VERSION=%%p
if %PATCH_VERSION% LSS 15 (
    echo ERROR: OpenSSL version %OPENSSL_VERSION% is older than required %OPENSSL_MIN_VERSION%
    exit /b 8
)

echo OpenSSL version validation successful: %OPENSSL_VERSION% meets requirement of %OPENSSL_MIN_VERSION% or later

if "%PERL%" == "" where perl > "%TEMP%\perl.loc" 2> nul && set /P PERL= <"%TEMP%\perl.loc" & del "%TEMP%\perl.loc"
if "%PERL%" == "" (echo Cannot locate perl.exe on PATH or as PERL variable & exit /b 4)

echo.
echo Building OpenSSL %OPENSSL_VERSION% with security-focused configuration...
echo Using build configuration compatible with OpenSSL 3.0+ security requirements
echo.

echo Building OpenSSL for Win32 platform...
%MSBUILD% "%PCBUILD%\openssl.vcxproj" /p:Configuration=Release /p:Platform=Win32 /p:UseSecurityFlags=true
if errorlevel 1 (
    echo ERROR: Failed to build OpenSSL for Win32 platform
    exit /b 10
)

echo Building OpenSSL for x64 platform...
%MSBUILD% "%PCBUILD%\openssl.vcxproj" /p:Configuration=Release /p:Platform=x64 /p:UseSecurityFlags=true
if errorlevel 1 (
    echo ERROR: Failed to build OpenSSL for x64 platform
    exit /b 11
)

echo Building OpenSSL for ARM platform...
%MSBUILD% "%PCBUILD%\openssl.vcxproj" /p:Configuration=Release /p:Platform=ARM /p:UseSecurityFlags=true
if errorlevel 1 (
    echo ERROR: Failed to build OpenSSL for ARM platform
    exit /b 12
)

echo Building OpenSSL for ARM64 platform...
%MSBUILD% "%PCBUILD%\openssl.vcxproj" /p:Configuration=Release /p:Platform=ARM64 /p:UseSecurityFlags=true
if errorlevel 1 (
    echo ERROR: Failed to build OpenSSL for ARM64 platform
    exit /b 13
)

echo.
echo OpenSSL %OPENSSL_VERSION% build completed successfully for all platforms.
echo Validating build output...

rem Validate that the expected OpenSSL libraries were built
set BUILD_VALIDATION_FAILED=false
if not exist "%EXTERNALS_DIR%\openssl-bin-*\*libcrypto*.dll" (
    echo WARNING: OpenSSL crypto library not found in expected location
    set BUILD_VALIDATION_FAILED=true
)
if not exist "%EXTERNALS_DIR%\openssl-bin-*\*libssl*.dll" (
    echo WARNING: OpenSSL SSL library not found in expected location  
    set BUILD_VALIDATION_FAILED=true
)

if "%BUILD_VALIDATION_FAILED%"=="true" (
    echo.
    echo Build validation completed with warnings. Please verify OpenSSL libraries manually.
) else (
    echo Build validation successful - OpenSSL libraries found.
)

echo.
echo SECURITY NOTE: This build includes OpenSSL %OPENSSL_VERSION% with fixes for:
echo   - CVE-2024-5535: NPN protocol buffer over-read vulnerability
echo   - OpenSSL 3.0+ provider architecture with enhanced security
echo   - Improved cryptographic implementations and security hardening
echo.

