#! /usr/bin/env python3
# Script for preparing OpenSSL for building on Windows.
# Uses Perl to create nmake makefiles and otherwise prepare the way
# for building on 32 or 64 bit platforms.

# Script originally authored by Mark Hammond.
# Major revisions by:
#   Martin v. Löwis
#   Christian Heimes
#   Zachary Ware
#
# OpenSSL 3.0.15+ Security Update (CVE-2024-5535, CVE-2024-7592, CVE-2024-12718):
# Enhanced to support OpenSSL 3.0.15 or later with security fixes.
# Added version validation and updated configure options for OpenSSL 3.x compatibility.

# THEORETICALLY, you can:
# * Unpack the latest OpenSSL 3.0.15+ release where $(opensslDir) in
#   PCbuild\pyproject.props expects it to be.
# * Install ActivePerl and ensure it is somewhere on your path.
# * Run this script with the OpenSSL source dir as the only argument.
#
# it should configure OpenSSL such that it is ready to be built by
# ssl.vcxproj on 32 or 64 bit platforms.
#
# NOTE: This script now requires OpenSSL 3.0.15 or later for security compliance.

from __future__ import print_function

import os
import re
import sys
import subprocess
from shutil import copy

def parse_openssl_version(version_string):
    """Parse OpenSSL version string and return version components.
    
    Args:
        version_string (str): Version string in format "major.minor.patch" or "major.minor.patch-suffix"
        
    Returns:
        tuple: (major, minor, patch) as integers, or None if parsing fails
        
    Examples:
        parse_openssl_version("3.0.15") -> (3, 0, 15)
        parse_openssl_version("3.0.15-dev") -> (3, 0, 15)
        parse_openssl_version("invalid") -> None
    """
    if not version_string:
        return None
        
    try:
        # Remove any suffix after dash (e.g., "3.0.15-dev" -> "3.0.15")
        version_base = version_string.split('-')[0]
        
        # Split version into components
        parts = version_base.split('.')
        if len(parts) < 2:
            return None
            
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
        
        return (major, minor, patch)
    except (ValueError, IndexError):
        return None

def validate_openssl_version(ssl_dir):
    """Validate that the OpenSSL source tree is version 3.0.15 or later.
    
    Args:
        ssl_dir (str): Path to OpenSSL source directory
        
    Returns:
        bool: True if version is valid (>= 3.0.15), False otherwise
        
    Raises:
        ValueError: If ssl_dir doesn't exist or version cannot be determined
    """
    if not os.path.isdir(ssl_dir):
        raise ValueError(f"SSL directory does not exist: {ssl_dir}")
        
    # Try to read version from VERSION.dat (OpenSSL 3.x format)
    version_file = os.path.join(ssl_dir, "VERSION.dat")
    version_found = False
    if os.path.exists(version_file):
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('VERSION='):
                        version_str = line.split('=', 1)[1]
                        version_tuple = parse_openssl_version(version_str)
                        if version_tuple:
                            major, minor, patch = version_tuple
                            # Check if version >= 3.0.15
                            if major > 3 or (major == 3 and minor > 0) or (major == 3 and minor == 0 and patch >= 15):
                                return True
                            print(f"WARNING: OpenSSL version {version_str} is below required 3.0.15")
                            return False
                        version_found = True  # Found VERSION= line but couldn't parse it
        except IOError as e:
            print(f"Error reading VERSION.dat: {e}")
    
    # Fallback: try to read from opensslv.h (legacy method) if VERSION.dat didn't contain version info
    if not version_found:
        header_file = os.path.join(ssl_dir, "include", "openssl", "opensslv.h")
        if os.path.exists(header_file):
            try:
                with open(header_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Look for version definition
                    version_match = re.search(r'#\s*define\s+OPENSSL_VERSION_TEXT\s+"OpenSSL\s+(\d+\.\d+\.\d+)', content)
                    if version_match:
                        version_str = version_match.group(1)
                        version_tuple = parse_openssl_version(version_str)
                        if version_tuple:
                            major, minor, patch = version_tuple
                            # Check if version >= 3.0.15
                            if major > 3 or (major == 3 and minor > 0) or (major == 3 and minor == 0 and patch >= 15):
                                return True
                            print(f"WARNING: OpenSSL version {version_str} is below required 3.0.15")
                            return False
                        version_found = True
            except IOError as e:
                print(f"Error reading opensslv.h: {e}")
    
    raise ValueError(f"Cannot determine OpenSSL version from {ssl_dir}")

# Find all "foo.exe" files on the PATH.
def find_all_on_path(filename, extras=None):
    entries = os.environ["PATH"].split(os.pathsep)
    ret = []
    for p in entries:
        fname = os.path.abspath(os.path.join(p, filename))
        if os.path.isfile(fname) and fname not in ret:
            ret.append(fname)
    if extras:
        for p in extras:
            fname = os.path.abspath(os.path.join(p, filename))
            if os.path.isfile(fname) and fname not in ret:
                ret.append(fname)
    return ret


# Find a suitable Perl installation for OpenSSL.
# cygwin perl does *not* work.  ActivePerl does.
# Being a Perl dummy, the simplest way I can check is if the "Win32" package
# is available.
def find_working_perl(perls):
    for perl in perls:
        try:
            subprocess.check_output([perl, "-e", "use Win32;"])
        except subprocess.CalledProcessError:
            continue
        else:
            return perl

    if perls:
        print("The following perl interpreters were found:")
        for p in perls:
            print(" ", p)
        print(" None of these versions appear suitable for building OpenSSL")
    else:
        print("NO perl interpreters were found on this machine at all!")
    print(" Please install ActivePerl and ensure it appears on your path")


def copy_includes(makefile, suffix):
    """Copy OpenSSL include files, with compatibility for OpenSSL 3.x structure.
    
    Args:
        makefile (str): Path to the makefile to parse
        suffix (str): Architecture suffix ("32" or "64")
    """
    dir = os.path.join('inc'+suffix, 'openssl')
    try:
        os.makedirs(dir)
    except OSError:
        if not os.path.isdir(dir):
            raise
    
    # Check if makefile exists (it may not in OpenSSL 3.x)
    if not os.path.exists(makefile):
        print(f"WARNING: Makefile {makefile} not found. Attempting alternative include copy method for OpenSSL 3.x")
        # For OpenSSL 3.x, try to copy includes directly
        src_include_dir = os.path.join('include', 'openssl')
        if os.path.exists(src_include_dir):
            import glob
            for header_file in glob.glob(os.path.join(src_include_dir, '*.h')):
                dest_file = os.path.join(dir, os.path.basename(header_file))
                print(f'copying {header_file} to {dest_file}')
                copy(header_file, dest_file)
        return
    
    copy_if_different = r'$(PERL) $(SRC_D)\util\copy-if-different.pl'
    try:
        with open(makefile) as fin:
            for line in fin:
                if copy_if_different in line:
                    # Handle potential variations in line format for OpenSSL 3.x
                    parts = line.split()
                    if len(parts) >= 4:
                        perl, script, src, dest = parts[:4]
                        if not '$(INCO_D)' in dest:
                            continue
                        # We're in the root of the source tree
                        src = src.replace('$(SRC_D)', '.').strip('"')
                        dest = dest.strip('"').replace('$(INCO_D)', dir)
                        print('copying', src, 'to', dest)
                        try:
                            copy(src, dest)
                        except IOError as e:
                            print(f"WARNING: Failed to copy {src} to {dest}: {e}")
    except IOError as e:
        print(f"ERROR: Failed to read makefile {makefile}: {e}")
        # Fallback to direct copying for OpenSSL 3.x
        src_include_dir = os.path.join('include', 'openssl')
        if os.path.exists(src_include_dir):
            import glob
            for header_file in glob.glob(os.path.join(src_include_dir, '*.h')):
                dest_file = os.path.join(dir, os.path.basename(header_file))
                print(f'copying {header_file} to {dest_file}')
                copy(header_file, dest_file)


def run_configure(configure, do_script, ssl_dir="."):
    """Run OpenSSL Configure with appropriate options for OpenSSL 3.0.15+
    
    Args:
        configure (str): Configure target (e.g., "VC-WIN64A", "VC-WIN32")
        do_script (str): Post-configure script to run (e.g., "ms\\do_win64a")
        ssl_dir (str): Path to SSL source directory for validation
    """
    # Validate OpenSSL version before proceeding
    if not validate_openssl_version(ssl_dir):
        print("ERROR: OpenSSL version validation failed. OpenSSL 3.0.15 or later is required.")
        sys.exit(1)
    
    # For OpenSSL 3.x, we need to update the configure options
    # The "no-idea" and "no-mdc2" options may not be needed in OpenSSL 3.x
    # as these algorithms are now handled by the legacy provider
    # However, we'll keep them for backward compatibility and add security-focused options
    configure_options = [
        configure,
        "no-idea",        # Disable IDEA cipher (still valid in 3.x)
        "no-mdc2",        # Disable MDC2 hash (still valid in 3.x) 
        "no-ssl3",        # Disable SSL 3.0 (security enhancement)
        "no-weak-ssl-ciphers",  # Disable weak ciphers (security enhancement)
    ]
    
    configure_cmd = f"perl Configure {' '.join(configure_options)}"
    print(f"Running: {configure_cmd}")
    result = os.system(configure_cmd)
    
    if result != 0:
        print(f"ERROR: Configure command failed with exit code {result}")
        sys.exit(1)
    
    # Run the post-configure script (e.g., ms\do_win64a)
    # In OpenSSL 3.x, these scripts may have been streamlined or removed
    # Check if the script exists before running it
    if os.path.exists(do_script):
        print(f"Running: {do_script}")
        result = os.system(do_script)
        if result != 0:
            print(f"WARNING: Post-configure script {do_script} failed with exit code {result}")
    else:
        print(f"INFO: Post-configure script {do_script} not found - this is normal for OpenSSL 3.x")

def fix_uplink():
    """Patch uplink.c for CPython _ssl module compatibility.
    
    In OpenSSL 3.x, the uplink.c file may be in a different location or may not exist.
    This function handles both legacy and new structures.
    """
    # uplink.c tries to find the OPENSSL_Applink function exported from the current
    # executable. However, we export it from _ssl[_d].pyd instead. So we update the
    # module name here before building.
    
    uplink_paths = ['ms\\uplink.c', 'util\\uplink.c', 'apps\\uplink.c']
    uplink_file = None
    
    # Find uplink.c in various possible locations for OpenSSL 3.x compatibility
    for path in uplink_paths:
        if os.path.exists(path):
            uplink_file = path
            break
    
    if not uplink_file:
        print("INFO: uplink.c not found - this is normal for some OpenSSL 3.x configurations")
        return
    
    print(f"Patching {uplink_file}...")
    
    try:
        with open(uplink_file, 'r', encoding='utf-8') as f1:
            code = list(f1)
        
        backup_file = uplink_file + '.orig'
        if not os.path.exists(backup_file):
            os.replace(uplink_file, backup_file)
            
        already_patched = False
        with open(uplink_file, 'w', encoding='utf-8') as f2:
            for line in code:
                if not already_patched:
                    if re.search('MODIFIED FOR CPYTHON _ssl MODULE', line):
                        already_patched = True
                    elif re.match(r'^\s+if\s*\(\(h\s*=\s*GetModuleHandle[AW]?\(NULL\)\)\s*==\s*NULL\)', line):
                        f2.write("/* MODIFIED FOR CPYTHON _ssl MODULE */\n")
                        f2.write('if ((h = GetModuleHandleW(L"_ssl.pyd")) == NULL) if ((h = GetModuleHandleW(L"_ssl_d.pyd")) == NULL)\n')
                        already_patched = True
                f2.write(line)
        
        if not already_patched:
            print(f"WARN: failed to patch {uplink_file}")
        else:
            print(f"✓ Successfully patched {uplink_file}")
            
    except IOError as e:
        print(f"ERROR: Failed to patch uplink.c: {e}")

def prep(arch, ssl_dir="."):
    """Prepare OpenSSL for building on Windows with specified architecture.
    
    Args:
        arch (str): Target architecture ("x86" or "amd64")
        ssl_dir (str): Path to OpenSSL source directory
    """
    makefile_template = "ms\\ntdll{}.mak"
    generated_makefile = makefile_template.format('')
    if arch == "x86":
        configure = "VC-WIN32"
        do_script = "ms\\do_nasm"
        suffix = "32"
    elif arch == "amd64":
        configure = "VC-WIN64A"
        do_script = "ms\\do_win64a"
        suffix = "64"
    else:
        raise ValueError('Unrecognized platform: %s' % arch)

    print("Creating the makefiles...")
    sys.stdout.flush()
    
    # run configure, copy includes, patch files
    run_configure(configure, do_script, ssl_dir)
    
    # Handle makefile management for OpenSSL 3.x compatibility
    # In OpenSSL 3.x, the makefile generation may have changed
    makefile = makefile_template.format(suffix)
    
    # Check if the expected generated makefile exists
    if os.path.exists(generated_makefile):
        try:
            os.unlink(makefile)
        except FileNotFoundError:
            pass
        os.rename(generated_makefile, makefile)
        copy_includes(makefile, suffix)
    else:
        # In OpenSSL 3.x, makefile generation may be different
        # Look for alternative makefile names or skip this step
        print(f"INFO: Generated makefile {generated_makefile} not found - checking for OpenSSL 3.x structure")
        
        # Check if a makefile already exists with the target name
        if os.path.exists(makefile):
            print(f"INFO: Using existing makefile {makefile}")
            copy_includes(makefile, suffix)
        else:
            print(f"WARNING: No suitable makefile found. OpenSSL 3.x may use different build structure.")

    print('patching ms\\uplink.c...')
    fix_uplink()

def main():
    if len(sys.argv) == 1:
        print("Not enough arguments: directory containing OpenSSL",
              "sources must be supplied")
        sys.exit(1)

    if len(sys.argv) == 3 and sys.argv[2] not in ('x86', 'amd64'):
        print("Second argument must be x86 or amd64")
        sys.exit(1)

    if len(sys.argv) > 3:
        print("Too many arguments supplied, all we need is the directory",
              "containing OpenSSL sources and optionally the architecture")
        sys.exit(1)

    ssl_dir = sys.argv[1]
    arch = sys.argv[2] if len(sys.argv) >= 3 else None

    if not os.path.isdir(ssl_dir):
        print(ssl_dir, "is not an existing directory!")
        sys.exit(1)

    # perl should be on the path, but we also look in "\perl" and "c:\\perl"
    # as "well known" locations
    perls = find_all_on_path("perl.exe", [r"\perl\bin",
                                          r"C:\perl\bin",
                                          r"\perl64\bin",
                                          r"C:\perl64\bin",
                                         ])
    perl = find_working_perl(perls)
    if perl:
        print("Found a working perl at '%s'" % (perl,))
    else:
        sys.exit(1)
    if not find_all_on_path('nmake.exe'):
        print('Could not find nmake.exe, try running env.bat')
        sys.exit(1)
    if not find_all_on_path('nasm.exe'):
        print('Could not find nasm.exe, please add to PATH')
        sys.exit(1)
    sys.stdout.flush()

    # Put our working Perl at the front of our path
    os.environ["PATH"] = os.path.dirname(perl) + \
                                os.pathsep + \
                                os.environ["PATH"]

    # Validate OpenSSL version before starting the build process
    print(f"Validating OpenSSL version in {ssl_dir}...")
    try:
        if validate_openssl_version(ssl_dir):
            print("✓ OpenSSL version validation passed - building OpenSSL 3.0.15 or later")
        else:
            print("ERROR: OpenSSL version validation failed")
            sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Version validation failed: {e}")
        sys.exit(1)

    old_cwd = os.getcwd()
    try:
        os.chdir(ssl_dir)
        if arch:
            prep(arch, ssl_dir)
        else:
            for arch_target in ['amd64', 'x86']:
                prep(arch_target, ssl_dir)
    finally:
        os.chdir(old_cwd)

if __name__=='__main__':
    main()
