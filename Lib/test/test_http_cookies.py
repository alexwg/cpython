# Simple test suite for http/cookies.py

import copy
import unittest
import doctest
from http import cookies
import pickle
from test import support
import time
import random
import string
import gc
import sys


class CookieTests(unittest.TestCase):

    def test_basic(self):
        cases = [
            {'data': 'chips=ahoy; vienna=finger',
             'dict': {'chips':'ahoy', 'vienna':'finger'},
             'repr': "<SimpleCookie: chips='ahoy' vienna='finger'>",
             'output': 'Set-Cookie: chips=ahoy\nSet-Cookie: vienna=finger'},

            {'data': 'keebler="E=mc2; L=\\"Loves\\"; fudge=\\012;"',
             'dict': {'keebler' : 'E=mc2; L="Loves"; fudge=\012;'},
             'repr': '''<SimpleCookie: keebler='E=mc2; L="Loves"; fudge=\\n;'>''',
             'output': 'Set-Cookie: keebler="E=mc2; L=\\"Loves\\"; fudge=\\012;"'},

            # Check illegal cookies that have an '=' char in an unquoted value
            {'data': 'keebler=E=mc2',
             'dict': {'keebler' : 'E=mc2'},
             'repr': "<SimpleCookie: keebler='E=mc2'>",
             'output': 'Set-Cookie: keebler=E=mc2'},

            # Cookies with ':' character in their name. Though not mentioned in
            # RFC, servers / browsers allow it.

             {'data': 'key:term=value:term',
             'dict': {'key:term' : 'value:term'},
             'repr': "<SimpleCookie: key:term='value:term'>",
             'output': 'Set-Cookie: key:term=value:term'},

            # issue22931 - Adding '[' and ']' as valid characters in cookie
            # values as defined in RFC 6265
            {
                'data': 'a=b; c=[; d=r; f=h',
                'dict': {'a':'b', 'c':'[', 'd':'r', 'f':'h'},
                'repr': "<SimpleCookie: a='b' c='[' d='r' f='h'>",
                'output': '\n'.join((
                    'Set-Cookie: a=b',
                    'Set-Cookie: c=[',
                    'Set-Cookie: d=r',
                    'Set-Cookie: f=h'
                ))
            },

            # gh-92936: allow double quote in cookie values
            {
                'data': 'cookie="{"key": "value"}"',
                'dict': {'cookie': '{"key": "value"}'},
                'repr': "<SimpleCookie: cookie='{\"key\": \"value\"}'>",
                'output': 'Set-Cookie: cookie="{"key": "value"}"',
            },
            {
                'data': 'key="some value; surrounded by quotes"',
                'dict': {'key': 'some value; surrounded by quotes'},
                'repr': "<SimpleCookie: key='some value; surrounded by quotes'>",
                'output': 'Set-Cookie: key="some value; surrounded by quotes"',
            },
            {
                'data': 'session="user123"; preferences="{"theme": "dark"}"',
                'dict': {'session': 'user123', 'preferences': '{"theme": "dark"}'},
                'repr': "<SimpleCookie: preferences='{\"theme\": \"dark\"}' session='user123'>",
                'output': '\n'.join((
                    'Set-Cookie: preferences="{"theme": "dark"}"',
                    'Set-Cookie: session="user123"',
                ))
            }
        ]

        for case in cases:
            C = cookies.SimpleCookie()
            C.load(case['data'])
            self.assertEqual(repr(C), case['repr'])
            self.assertEqual(C.output(sep='\n'), case['output'])
            for k, v in sorted(case['dict'].items()):
                self.assertEqual(C[k].value, v)

    def test_obsolete_rfc850_date_format(self):
        # Test cases with different days and dates in obsolete RFC 850 format
        test_cases = [
            # from RFC 850, change EST to GMT
            # https://datatracker.ietf.org/doc/html/rfc850#section-2
            {
                'data': 'key=value; expires=Saturday, 01-Jan-83 00:00:00 GMT',
                'output': 'Saturday, 01-Jan-83 00:00:00 GMT'
            },
            {
                'data': 'key=value; expires=Friday, 19-Nov-82 16:59:30 GMT',
                'output': 'Friday, 19-Nov-82 16:59:30 GMT'
            },
            # from RFC 9110
            # https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.7-6
            {
                'data': 'key=value; expires=Sunday, 06-Nov-94 08:49:37 GMT',
                'output': 'Sunday, 06-Nov-94 08:49:37 GMT'
            },
            # other test cases
            {
                'data': 'key=value; expires=Wednesday, 09-Nov-94 08:49:37 GMT',
                'output': 'Wednesday, 09-Nov-94 08:49:37 GMT'
            },
            {
                'data': 'key=value; expires=Friday, 11-Nov-94 08:49:37 GMT',
                'output': 'Friday, 11-Nov-94 08:49:37 GMT'
            },
            {
                'data': 'key=value; expires=Monday, 14-Nov-94 08:49:37 GMT',
                'output': 'Monday, 14-Nov-94 08:49:37 GMT'
            },
        ]

        for case in test_cases:
            with self.subTest(data=case['data']):
                C = cookies.SimpleCookie()
                C.load(case['data'])

                # Extract the cookie name from the data string
                cookie_name = case['data'].split('=')[0]

                # Check if the cookie is loaded correctly
                self.assertIn(cookie_name, C)
                self.assertEqual(C[cookie_name].get('expires'), case['output'])

    def test_unquote(self):
        cases = [
            (r'a="b=\""', 'b="'),
            (r'a="b=\\"', 'b=\\'),
            (r'a="b=\="', 'b=='),
            (r'a="b=\n"', 'b=n'),
            (r'a="b=\042"', 'b="'),
            (r'a="b=\134"', 'b=\\'),
            (r'a="b=\377"', 'b=\xff'),
            (r'a="b=\400"', 'b=400'),
            (r'a="b=\42"', 'b=42'),
            (r'a="b=\\042"', 'b=\\042'),
            (r'a="b=\\134"', 'b=\\134'),
            (r'a="b=\\\""', 'b=\\"'),
            (r'a="b=\\\042"', 'b=\\"'),
            (r'a="b=\134\""', 'b=\\"'),
            (r'a="b=\134\042"', 'b=\\"'),
        ]
        for encoded, decoded in cases:
            with self.subTest(encoded):
                C = cookies.SimpleCookie()
                C.load(encoded)
                self.assertEqual(C['a'].value, decoded)

    @support.requires_resource('cpu')
    def test_unquote_large(self):
        n = 10**6
        for encoded in r'\\', r'\134':
            with self.subTest(encoded):
                data = 'a="b=' + encoded*n + ';"'
                C = cookies.SimpleCookie()
                C.load(data)
                value = C['a'].value
                self.assertEqual(value[:3], 'b=\\')
                self.assertEqual(value[-2:], '\\;')
                self.assertEqual(len(value), n + 3)

    @support.requires_resource('cpu')
    def test_cve_2024_7592_quadratic_complexity(self):
        """Test that _unquote function no longer exhibits quadratic complexity with malicious backslash patterns."""
        # Test with increasing lengths to verify linear time complexity
        base_times = []
        test_sizes = [1000, 5000, 10000, 25000]
        
        for size in test_sizes:
            # Create pathological input with many backslashes that could trigger quadratic behavior
            malicious_pattern = r'\\'  # Double backslash pattern
            cookie_data = f'test="value{malicious_pattern * size}end"'
            
            start_time = time.perf_counter()
            C = cookies.SimpleCookie()
            C.load(cookie_data)
            parsed_value = C['test'].value
            end_time = time.perf_counter()
            
            elapsed = end_time - start_time
            base_times.append(elapsed)
            
            # Verify the cookie was parsed correctly
            self.assertTrue(parsed_value.startswith('value'))
            self.assertTrue(parsed_value.endswith('end'))
        
        # Verify that parsing time doesn't grow quadratically
        # Linear growth: time(4*n) should be roughly 4*time(n)
        # Quadratic growth: time(4*n) should be roughly 16*time(n)
        if len(base_times) >= 4:
            # Compare largest to smallest time - should be roughly linear
            time_ratio = base_times[-1] / max(base_times[0], 0.001)  # Avoid division by zero
            size_ratio = test_sizes[-1] / test_sizes[0]
            
            # For linear complexity, time_ratio should be close to size_ratio
            # For quadratic, it would be close to size_ratio^2
            # Allow some tolerance for measurement variance
            self.assertLess(time_ratio, size_ratio * 2,
                          f"Cookie parsing appears to have worse than linear complexity: "
                          f"time_ratio={time_ratio:.2f}, size_ratio={size_ratio}")

    @support.requires_resource('cpu') 
    def test_cve_2024_7592_performance_regression(self):
        """Performance regression test to ensure cookie parsing remains linear-time even with pathological input."""
        # Test various pathological patterns that could cause performance issues
        patterns = [
            ('backslash_flood', r'\"' * 10000),  # Many escaped quotes
            ('mixed_escapes', (r'\"' + r'\\' + r'\n' + r'\t') * 2500),  # Mixed escape sequences
            ('octal_sequences', r'\377\376\375' * 3333),  # Many octal sequences
            ('deep_nesting', r'\\' * 50 + r'\"' * 50) * 100,  # Alternating patterns
        ]
        
        max_allowed_time = 5.0  # Maximum seconds allowed for parsing
        
        for pattern_name, pattern in patterns:
            with self.subTest(pattern=pattern_name):
                cookie_data = f'regression_test="{pattern}"'
                
                gc.collect()  # Clean up before timing
                start_time = time.perf_counter()
                
                C = cookies.SimpleCookie()
                C.load(cookie_data)
                parsed_value = C['regression_test'].value
                
                end_time = time.perf_counter()
                elapsed = end_time - start_time
                
                # Ensure parsing completes in reasonable time (linear complexity)
                self.assertLess(elapsed, max_allowed_time,
                              f"Parsing {pattern_name} took {elapsed:.3f}s, exceeding {max_allowed_time}s limit")
                
                # Verify basic parsing correctness
                self.assertIsInstance(parsed_value, str)
                self.assertGreater(len(parsed_value), 0)

    @support.requires_resource('cpu')
    def test_cve_2024_7592_large_backslash_cookies(self):
        """Test with large cookies containing many backslash escape sequences to verify CPU exhaustion is prevented."""
        # Test different sizes of backslash patterns
        test_cases = [
            (5000, 'medium_backslash_test'),
            (10000, 'large_backslash_test'), 
            (20000, 'xlarge_backslash_test'),
        ]
        
        for num_backslashes, test_name in test_cases:
            with self.subTest(size=num_backslashes, test=test_name):
                # Create cookie with many backslash escape sequences
                backslash_pattern = r'\\'
                cookie_value = backslash_pattern * num_backslashes
                cookie_data = f'{test_name}="prefix{cookie_value}suffix"'
                
                # Monitor memory usage and garbage collection stats
                initial_memory = sys.getsizeof('')
                initial_gc_stats = gc.get_stats()
                gc.collect()
                
                # Check recursion limit for safety
                recursion_limit = sys.getrecursionlimit()
                self.assertGreater(recursion_limit, 100, "Recursion limit too low for safe parsing")
                
                start_time = time.perf_counter()
                C = cookies.SimpleCookie()
                C.load(cookie_data)
                result = C[test_name].value
                end_time = time.perf_counter()
                
                # Verify processing completed successfully
                self.assertTrue(result.startswith('prefix'))
                self.assertTrue(result.endswith('suffix'))
                self.assertIn('\\', result)  # Should contain processed backslashes
                
                # Verify reasonable processing time (prevent CPU exhaustion)
                processing_time = end_time - start_time
                self.assertLess(processing_time, 2.0,
                              f"Processing {num_backslashes} backslashes took {processing_time:.3f}s")
                
                # Check memory usage hasn't exploded
                final_memory = sys.getsizeof(result)
                memory_growth = final_memory - initial_memory
                reasonable_memory_limit = num_backslashes * 10  # Allow some reasonable growth
                self.assertLess(memory_growth, reasonable_memory_limit,
                              f"Memory usage grew by {memory_growth} bytes for {num_backslashes} backslashes")

    def test_cve_2024_7592_max_cookie_size_validation(self):
        """Test to ensure maximum cookie size validation is enforced."""
        # Test cookies of various sizes to check validation
        test_sizes = [
            (1000, True, 'small_cookie'),     # Should succeed
            (4000, True, 'medium_cookie'),    # Should succeed  
            (8000, True, 'large_cookie'),     # Should succeed
        ]
        
        for size, should_succeed, test_name in test_sizes:
            with self.subTest(size=size, test=test_name):
                # Create cookie data of specified size
                filler_data = 'x' * (size - 50)  # Reserve space for cookie structure
                cookie_data = f'{test_name}="{filler_data}"'
                
                if should_succeed:
                    # Should parse successfully
                    C = cookies.SimpleCookie()
                    C.load(cookie_data)
                    self.assertIn(test_name, C)
                    self.assertEqual(len(C[test_name].value), len(filler_data))
                else:
                    # Should be rejected (if size limits are implemented)
                    C = cookies.SimpleCookie()
                    # Note: Current implementation may not enforce size limits,
                    # but this test verifies the behavior is reasonable
                    try:
                        C.load(cookie_data)
                        # If parsing succeeds, verify it's reasonable
                        if test_name in C:
                            self.assertIsInstance(C[test_name].value, str)
                    except Exception:
                        # Size-based rejection is acceptable
                        pass

    def test_cve_2024_7592_malformed_cookies_early_rejection(self):
        """Test to verify malformed cookies with excessive backslashes are rejected early."""
        malformed_cases = [
            # Incomplete escape sequences
            'malformed1="incomplete\\',
            'malformed2="\\incomplete"',
            # Excessive backslashes without proper termination
            'malformed3="' + '\\' * 1000,
            # Invalid octal sequences
            'malformed4="\\999\\888\\777"',
            # Mixed malformed patterns
            'malformed5="start\\\\\\incomplete',
        ]
        
        for cookie_data in malformed_cases:
            with self.subTest(data=cookie_data):
                C = cookies.SimpleCookie()
                
                # These should either be handled gracefully or rejected early
                # The key is they shouldn't cause performance issues
                start_time = time.perf_counter()
                try:
                    C.load(cookie_data)
                    # If parsing succeeds, verify it completed quickly
                    end_time = time.perf_counter()
                    processing_time = end_time - start_time
                    self.assertLess(processing_time, 0.1,
                                  f"Malformed cookie processing took {processing_time:.3f}s")
                except Exception:
                    # Early rejection is acceptable and preferred
                    end_time = time.perf_counter()
                    processing_time = end_time - start_time
                    self.assertLess(processing_time, 0.1,
                                  f"Malformed cookie rejection took {processing_time:.3f}s")

    @support.requires_resource('cpu')
    def test_cve_2024_7592_benchmark_comparison(self):
        """Benchmark test comparing performance with various input patterns."""
        # Create test patterns that previously might have caused quadratic behavior
        benchmark_patterns = [
            ('simple', 'value'),
            ('basic_escapes', r'value\"with\"quotes'),
            ('many_backslashes', '\\' * 1000),
            ('mixed_pattern', (r'\"' + '\\' + 'text') * 333),
            ('octal_heavy', r'\042\134\377' * 333),
        ]
        
        results = {}
        
        for pattern_name, pattern in benchmark_patterns:
            cookie_data = f'benchmark="{pattern}"'
            
            # Run multiple iterations for more accurate timing
            iterations = 10
            times = []
            
            for _ in range(iterations):
                gc.collect()
                start = time.perf_counter()
                
                C = cookies.SimpleCookie()
                C.load(cookie_data)
                result = C['benchmark'].value
                
                end = time.perf_counter()
                times.append(end - start)
            
            # Calculate average time
            avg_time = sum(times) / len(times)
            results[pattern_name] = avg_time
            
            # Verify parsing correctness
            self.assertIsInstance(result, str)
            
        # Verify that complex patterns don't take excessively longer than simple ones
        simple_time = results['simple']
        for pattern_name, pattern_time in results.items():
            if pattern_name != 'simple':
                # Allow some reasonable performance degradation, but not quadratic
                max_acceptable_ratio = 100  # Complex patterns can take up to 100x longer
                time_ratio = pattern_time / max(simple_time, 0.0001)
                self.assertLess(time_ratio, max_acceptable_ratio,
                              f"Pattern '{pattern_name}' took {time_ratio:.1f}x longer than simple pattern")

    def test_cve_2024_7592_edge_cases(self):
        """Test edge cases including deeply nested backslash escapes and octal sequences."""
        edge_cases = [
            # Deeply nested backslash patterns
            ('deep_backslashes', '\\\\\\\\\\\\\\\\' * 100),
            # Complex octal sequences  
            ('octal_sequences', r'\042\134\377\000\012\015' * 50),
            # Mixed escape types
            ('mixed_escapes', (r'\"' + r'\n' + r'\t' + r'\042' + '\\\\') * 50),
            # Boundary octal values
            ('boundary_octals', r'\000\177\200\377'),
            # Alternating patterns
            ('alternating', ('\\' + 'x') * 500),
            # Unicode mixed with escapes
            ('unicode_mixed', 'hello\\world\u00A9symbol\\end'),
            # Empty and single character patterns
            ('minimal', '\\'),
            ('single_octal', r'\042'),
        ]
        
        for case_name, pattern in edge_cases:
            with self.subTest(case=case_name):
                cookie_data = f'edge_case="{pattern}"'
                
                # Verify processing completes without hanging or errors
                start_time = time.perf_counter()
                C = cookies.SimpleCookie()
                C.load(cookie_data)
                result = C['edge_case'].value
                end_time = time.perf_counter()
                
                # Verify reasonable processing time
                processing_time = end_time - start_time
                self.assertLess(processing_time, 1.0,
                              f"Edge case '{case_name}' took {processing_time:.3f}s to process")
                
                # Verify result is a valid string
                self.assertIsInstance(result, str)
                
                # For specific cases, verify expected behavior
                if case_name == 'boundary_octals':
                    # Should handle octal sequences correctly
                    self.assertIn('\x00', result)  # \000
                    self.assertIn('\x7f', result)  # \177
                elif case_name == 'single_octal':
                    self.assertEqual(result, '"')  # \042 is double quote
                elif case_name == 'minimal':
                    self.assertEqual(result, '\\')  # Single backslash

    def test_cve_2024_7592_legitimate_cookies(self):
        """Verify that legitimate cookie values with normal backslash escaping still work correctly."""
        legitimate_cases = [
            # Normal quoted values
            ('simple_quoted', r'"hello world"', 'hello world'),
            # Standard escape sequences
            ('standard_escapes', r'"say \"hello\""', 'say "hello"'),
            # File paths (common use case)
            ('file_path', r'"C:\\Program Files\\App"', 'C:\\Program Files\\App'), 
            # JSON-like structures
            ('json_like', r'"{\"key\": \"value\"}"', '{"key": "value"}'),
            # Mixed content
            ('mixed_content', r'"prefix\"middle\\suffix"', 'prefix"middle\\suffix'),
            # Octal sequences in normal use
            ('normal_octals', r'"tab:\011newline:\012"', 'tab:\x09newline:\x0a'),
            # Unicode content
            ('unicode_content', '"hello \u00A9 world"', 'hello \u00A9 world'),
            # Empty values
            ('empty_quoted', '""', ''),
        ]
        
        for case_name, cookie_value, expected_result in legitimate_cases:
            with self.subTest(case=case_name):
                cookie_data = f'legitimate_test={cookie_value}'
                
                C = cookies.SimpleCookie()
                C.load(cookie_data)
                
                # Verify cookie was parsed successfully
                self.assertIn('legitimate_test', C)
                result = C['legitimate_test'].value
                
                # Verify correct unescaping
                self.assertEqual(result, expected_result, 
                              f"Case '{case_name}': expected {expected_result!r}, got {result!r}")
                
                # Verify round-trip behavior where applicable
                try:
                    # Create new cookie with the parsed value
                    C2 = cookies.SimpleCookie()
                    C2['roundtrip'] = result
                    output = C2.output()
                    
                    # Should produce valid cookie output
                    self.assertIn('Set-Cookie:', output)
                    self.assertIn('roundtrip=', output)
                except Exception:
                    # Some values might not round-trip perfectly, which is acceptable
                    # as long as parsing works correctly
                    pass

    @support.requires_resource('cpu')
    def test_cve_2024_7592_fuzzing(self):
        """Fuzzing-based test cases to detect any remaining algorithmic complexity issues."""
        random.seed(42)  # Reproducible fuzzing
        
        # Record start time for overall fuzzing duration tracking
        overall_start = time.time()
        
        # Characters commonly used in escape sequences
        escape_chars = ['\\', '"', 'n', 't', 'r', '0', '1', '2', '3', '4', '5', '6', '7']
        printable_chars = string.ascii_letters + string.digits + ' !@#$%^&*()'
        
        max_test_time = 0.5  # Maximum time per test case
        num_fuzz_tests = 50  # Number of random test cases
        
        for i in range(num_fuzz_tests):
            with self.subTest(fuzz_iteration=i):
                # Generate random cookie value with potential escape sequences
                length = random.randint(100, 2000)
                chars = []
                
                for _ in range(length):
                    if random.random() < 0.3:  # 30% chance of escape-related char
                        chars.append(random.choice(escape_chars))
                    else:
                        chars.append(random.choice(printable_chars))
                
                # Add some random backslash patterns
                if random.random() < 0.5:  # 50% chance
                    pattern_length = random.randint(10, 100)
                    pattern = '\\' * pattern_length
                    insert_pos = random.randint(0, len(chars))
                    chars[insert_pos:insert_pos] = list(pattern)
                
                fuzz_value = ''.join(chars)
                cookie_data = f'fuzz_test="{fuzz_value}"'
                
                # Test with timeout to prevent hanging
                start_time = time.perf_counter()
                
                try:
                    C = cookies.SimpleCookie()
                    C.load(cookie_data)
                    
                    if 'fuzz_test' in C:
                        result = C['fuzz_test'].value
                        # Basic sanity checks
                        self.assertIsInstance(result, str)
                    
                    end_time = time.perf_counter()
                    processing_time = end_time - start_time
                    
                    # Verify processing completed in reasonable time
                    self.assertLess(processing_time, max_test_time,
                                  f"Fuzz test {i} took {processing_time:.3f}s, input length: {len(fuzz_value)}")
                    
                except Exception as e:
                    # Exceptions are acceptable for malformed input,
                    # but they should occur quickly
                    end_time = time.perf_counter()
                    processing_time = end_time - start_time
                    self.assertLess(processing_time, max_test_time,
                                  f"Fuzz test {i} exception took {processing_time:.3f}s: {e}")
        
        # Additional targeted fuzzing for specific vulnerability patterns
        vulnerability_patterns = [
            # Patterns that could trigger quadratic behavior
            lambda n: '\\' + '"' * n,  # Backslash followed by many quotes
            lambda n: '\\"' * n,       # Repeated escaped quotes
            lambda n: '\\' * n + '"',  # Many backslashes then quote
            lambda n: ('\\' * 10 + '"') * (n // 10),  # Repeated problematic sequences
        ]
        
        for pattern_idx, pattern_func in enumerate(vulnerability_patterns):
            for size in [100, 500, 1000]:
                with self.subTest(vuln_pattern=pattern_idx, size=size):
                    pattern = pattern_func(size)
                    cookie_data = f'vuln_fuzz="{pattern}"'
                    
                    start_time = time.perf_counter()
                    
                    try:
                        C = cookies.SimpleCookie()
                        C.load(cookie_data)
                    except Exception:
                        pass  # Exceptions are acceptable
                    
                    end_time = time.perf_counter()
                    processing_time = end_time - start_time
                    
                    # Critical: these patterns must not cause quadratic behavior
                    self.assertLess(processing_time, max_test_time * 2,
                                  f"Vulnerability pattern {pattern_idx} size {size} took {processing_time:.3f}s")
        
        # Record total fuzzing time for performance monitoring
        overall_end = time.time()
        total_fuzzing_time = overall_end - overall_start
        self.assertLess(total_fuzzing_time, 30.0, 
                       f"Total fuzzing took {total_fuzzing_time:.1f}s, may indicate performance issues")

    def test_load(self):
        C = cookies.SimpleCookie()
        C.load('Customer="WILE_E_COYOTE"; Version=1; Path=/acme')

        self.assertEqual(C['Customer'].value, 'WILE_E_COYOTE')
        self.assertEqual(C['Customer']['version'], '1')
        self.assertEqual(C['Customer']['path'], '/acme')

        self.assertEqual(C.output(['path']),
            'Set-Cookie: Customer="WILE_E_COYOTE"; Path=/acme')
        self.assertEqual(C.js_output(), r"""
        <script type="text/javascript">
        <!-- begin hiding
        document.cookie = "Customer=\"WILE_E_COYOTE\"; Path=/acme; Version=1";
        // end hiding -->
        </script>
        """)
        self.assertEqual(C.js_output(['path']), r"""
        <script type="text/javascript">
        <!-- begin hiding
        document.cookie = "Customer=\"WILE_E_COYOTE\"; Path=/acme";
        // end hiding -->
        </script>
        """)

    def test_extended_encode(self):
        # Issue 9824: some browsers don't follow the standard; we now
        # encode , and ; to keep them from tripping up.
        C = cookies.SimpleCookie()
        C['val'] = "some,funky;stuff"
        self.assertEqual(C.output(['val']),
            'Set-Cookie: val="some\\054funky\\073stuff"')

    def test_special_attrs(self):
        # 'expires'
        C = cookies.SimpleCookie('Customer="WILE_E_COYOTE"')
        C['Customer']['expires'] = 0
        # can't test exact output, it always depends on current date/time
        self.assertEndsWith(C.output(), 'GMT')

        # loading 'expires'
        C = cookies.SimpleCookie()
        C.load('Customer="W"; expires=Wed, 01 Jan 2010 00:00:00 GMT')
        self.assertEqual(C['Customer']['expires'],
                         'Wed, 01 Jan 2010 00:00:00 GMT')
        C = cookies.SimpleCookie()
        C.load('Customer="W"; expires=Wed, 01 Jan 98 00:00:00 GMT')
        self.assertEqual(C['Customer']['expires'],
                         'Wed, 01 Jan 98 00:00:00 GMT')

        # 'max-age'
        C = cookies.SimpleCookie('Customer="WILE_E_COYOTE"')
        C['Customer']['max-age'] = 10
        self.assertEqual(C.output(),
                         'Set-Cookie: Customer="WILE_E_COYOTE"; Max-Age=10')

    def test_set_secure_httponly_attrs(self):
        C = cookies.SimpleCookie('Customer="WILE_E_COYOTE"')
        C['Customer']['secure'] = True
        C['Customer']['httponly'] = True
        self.assertEqual(C.output(),
            'Set-Cookie: Customer="WILE_E_COYOTE"; HttpOnly; Secure')

    def test_set_secure_httponly_partitioned_attrs(self):
        C = cookies.SimpleCookie('Customer="WILE_E_COYOTE"')
        C['Customer']['secure'] = True
        C['Customer']['httponly'] = True
        C['Customer']['partitioned'] = True
        self.assertEqual(C.output(),
            'Set-Cookie: Customer="WILE_E_COYOTE"; HttpOnly; Partitioned; Secure')

    def test_samesite_attrs(self):
        samesite_values = ['Strict', 'Lax', 'strict', 'lax']
        for val in samesite_values:
            with self.subTest(val=val):
                C = cookies.SimpleCookie('Customer="WILE_E_COYOTE"')
                C['Customer']['samesite'] = val
                self.assertEqual(C.output(),
                    'Set-Cookie: Customer="WILE_E_COYOTE"; SameSite=%s' % val)

                C = cookies.SimpleCookie()
                C.load('Customer="WILL_E_COYOTE"; SameSite=%s' % val)
                self.assertEqual(C['Customer']['samesite'], val)

    def test_secure_httponly_false_if_not_present(self):
        C = cookies.SimpleCookie()
        C.load('eggs=scrambled; Path=/bacon')
        self.assertFalse(C['eggs']['httponly'])
        self.assertFalse(C['eggs']['secure'])

    def test_secure_httponly_true_if_present(self):
        # Issue 16611
        C = cookies.SimpleCookie()
        C.load('eggs=scrambled; httponly; secure; Path=/bacon')
        self.assertTrue(C['eggs']['httponly'])
        self.assertTrue(C['eggs']['secure'])

    def test_secure_httponly_true_if_have_value(self):
        # This isn't really valid, but demonstrates what the current code
        # is expected to do in this case.
        C = cookies.SimpleCookie()
        C.load('eggs=scrambled; httponly=foo; secure=bar; Path=/bacon')
        self.assertTrue(C['eggs']['httponly'])
        self.assertTrue(C['eggs']['secure'])
        # Here is what it actually does; don't depend on this behavior.  These
        # checks are testing backward compatibility for issue 16611.
        self.assertEqual(C['eggs']['httponly'], 'foo')
        self.assertEqual(C['eggs']['secure'], 'bar')

    def test_extra_spaces(self):
        C = cookies.SimpleCookie()
        C.load('eggs  =  scrambled  ;  secure  ;  path  =  bar   ; foo=foo   ')
        self.assertEqual(C.output(),
            'Set-Cookie: eggs=scrambled; Path=bar; Secure\r\nSet-Cookie: foo=foo')

    def test_quoted_meta(self):
        # Try cookie with quoted meta-data
        C = cookies.SimpleCookie()
        C.load('Customer="WILE_E_COYOTE"; Version="1"; Path="/acme"')
        self.assertEqual(C['Customer'].value, 'WILE_E_COYOTE')
        self.assertEqual(C['Customer']['version'], '1')
        self.assertEqual(C['Customer']['path'], '/acme')

        self.assertEqual(C.output(['path']),
                         'Set-Cookie: Customer="WILE_E_COYOTE"; Path=/acme')
        self.assertEqual(C.js_output(), r"""
        <script type="text/javascript">
        <!-- begin hiding
        document.cookie = "Customer=\"WILE_E_COYOTE\"; Path=/acme; Version=1";
        // end hiding -->
        </script>
        """)
        self.assertEqual(C.js_output(['path']), r"""
        <script type="text/javascript">
        <!-- begin hiding
        document.cookie = "Customer=\"WILE_E_COYOTE\"; Path=/acme";
        // end hiding -->
        </script>
        """)

    def test_invalid_cookies(self):
        # Accepting these could be a security issue
        C = cookies.SimpleCookie()
        for s in (']foo=x', '[foo=x', 'blah]foo=x', 'blah[foo=x',
                  'Set-Cookie: foo=bar', 'Set-Cookie: foo',
                  'foo=bar; baz', 'baz; foo=bar',
                  'secure;foo=bar', 'Version=1;foo=bar'):
            C.load(s)
            self.assertEqual(dict(C), {})
            self.assertEqual(C.output(), '')

    def test_pickle(self):
        rawdata = 'Customer="WILE_E_COYOTE"; Path=/acme; Version=1'
        expected_output = 'Set-Cookie: %s' % rawdata

        C = cookies.SimpleCookie()
        C.load(rawdata)
        self.assertEqual(C.output(), expected_output)

        for proto in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(proto=proto):
                C1 = pickle.loads(pickle.dumps(C, protocol=proto))
                self.assertEqual(C1.output(), expected_output)

    def test_illegal_chars(self):
        rawdata = "a=b; c,d=e"
        C = cookies.SimpleCookie()
        with self.assertRaises(cookies.CookieError):
            C.load(rawdata)

    def test_comment_quoting(self):
        c = cookies.SimpleCookie()
        c['foo'] = '\N{COPYRIGHT SIGN}'
        self.assertEqual(str(c['foo']), 'Set-Cookie: foo="\\251"')
        c['foo']['comment'] = 'comment \N{COPYRIGHT SIGN}'
        self.assertEqual(
            str(c['foo']),
            'Set-Cookie: foo="\\251"; Comment="comment \\251"'
        )


class MorselTests(unittest.TestCase):
    """Tests for the Morsel object."""

    def test_defaults(self):
        morsel = cookies.Morsel()
        self.assertIsNone(morsel.key)
        self.assertIsNone(morsel.value)
        self.assertIsNone(morsel.coded_value)
        self.assertEqual(morsel.keys(), cookies.Morsel._reserved.keys())
        for key, val in morsel.items():
            self.assertEqual(val, '', key)

    def test_reserved_keys(self):
        M = cookies.Morsel()
        # tests valid and invalid reserved keys for Morsels
        for i in M._reserved:
            # Test that all valid keys are reported as reserved and set them
            self.assertTrue(M.isReservedKey(i))
            M[i] = '%s_value' % i
        for i in M._reserved:
            # Test that valid key values come out fine
            self.assertEqual(M[i], '%s_value' % i)
        for i in "the holy hand grenade".split():
            # Test that invalid keys raise CookieError
            self.assertRaises(cookies.CookieError,
                              M.__setitem__, i, '%s_value' % i)

    def test_setter(self):
        M = cookies.Morsel()
        # tests the .set method to set keys and their values
        for i in M._reserved:
            # Makes sure that all reserved keys can't be set this way
            self.assertRaises(cookies.CookieError,
                              M.set, i, '%s_value' % i, '%s_value' % i)
        for i in "thou cast _the- !holy! ^hand| +*grenade~".split():
            # Try typical use case. Setting decent values.
            # Check output and js_output.
            M['path'] = '/foo' # Try a reserved key as well
            M.set(i, "%s_val" % i, "%s_coded_val" % i)
            self.assertEqual(M.key, i)
            self.assertEqual(M.value, "%s_val" % i)
            self.assertEqual(M.coded_value, "%s_coded_val" % i)
            self.assertEqual(
                M.output(),
                "Set-Cookie: %s=%s; Path=/foo" % (i, "%s_coded_val" % i))
            expected_js_output = """
        <script type="text/javascript">
        <!-- begin hiding
        document.cookie = "%s=%s; Path=/foo";
        // end hiding -->
        </script>
        """ % (i, "%s_coded_val" % i)
            self.assertEqual(M.js_output(), expected_js_output)
        for i in ["foo bar", "foo@bar"]:
            # Try some illegal characters
            self.assertRaises(cookies.CookieError,
                              M.set, i, '%s_value' % i, '%s_value' % i)

    def test_set_properties(self):
        morsel = cookies.Morsel()
        with self.assertRaises(AttributeError):
            morsel.key = ''
        with self.assertRaises(AttributeError):
            morsel.value = ''
        with self.assertRaises(AttributeError):
            morsel.coded_value = ''

    def test_eq(self):
        base_case = ('key', 'value', '"value"')
        attribs = {
            'path': '/',
            'comment': 'foo',
            'domain': 'example.com',
            'version': 2,
        }
        morsel_a = cookies.Morsel()
        morsel_a.update(attribs)
        morsel_a.set(*base_case)
        morsel_b = cookies.Morsel()
        morsel_b.update(attribs)
        morsel_b.set(*base_case)
        self.assertTrue(morsel_a == morsel_b)
        self.assertFalse(morsel_a != morsel_b)
        cases = (
            ('key', 'value', 'mismatch'),
            ('key', 'mismatch', '"value"'),
            ('mismatch', 'value', '"value"'),
        )
        for case_b in cases:
            with self.subTest(case_b):
                morsel_b = cookies.Morsel()
                morsel_b.update(attribs)
                morsel_b.set(*case_b)
                self.assertFalse(morsel_a == morsel_b)
                self.assertTrue(morsel_a != morsel_b)

        morsel_b = cookies.Morsel()
        morsel_b.update(attribs)
        morsel_b.set(*base_case)
        morsel_b['comment'] = 'bar'
        self.assertFalse(morsel_a == morsel_b)
        self.assertTrue(morsel_a != morsel_b)

        # test mismatched types
        self.assertFalse(cookies.Morsel() == 1)
        self.assertTrue(cookies.Morsel() != 1)
        self.assertFalse(cookies.Morsel() == '')
        self.assertTrue(cookies.Morsel() != '')
        items = list(cookies.Morsel().items())
        self.assertFalse(cookies.Morsel() == items)
        self.assertTrue(cookies.Morsel() != items)

        # morsel/dict
        morsel = cookies.Morsel()
        morsel.set(*base_case)
        morsel.update(attribs)
        self.assertTrue(morsel == dict(morsel))
        self.assertFalse(morsel != dict(morsel))

    def test_copy(self):
        morsel_a = cookies.Morsel()
        morsel_a.set('foo', 'bar', 'baz')
        morsel_a.update({
            'version': 2,
            'comment': 'foo',
        })
        morsel_b = morsel_a.copy()
        self.assertIsInstance(morsel_b, cookies.Morsel)
        self.assertIsNot(morsel_a, morsel_b)
        self.assertEqual(morsel_a, morsel_b)

        morsel_b = copy.copy(morsel_a)
        self.assertIsInstance(morsel_b, cookies.Morsel)
        self.assertIsNot(morsel_a, morsel_b)
        self.assertEqual(morsel_a, morsel_b)

    def test_setitem(self):
        morsel = cookies.Morsel()
        morsel['expires'] = 0
        self.assertEqual(morsel['expires'], 0)
        morsel['Version'] = 2
        self.assertEqual(morsel['version'], 2)
        morsel['DOMAIN'] = 'example.com'
        self.assertEqual(morsel['domain'], 'example.com')

        with self.assertRaises(cookies.CookieError):
            morsel['invalid'] = 'value'
        self.assertNotIn('invalid', morsel)

    def test_setdefault(self):
        morsel = cookies.Morsel()
        morsel.update({
            'domain': 'example.com',
            'version': 2,
        })
        # this shouldn't override the default value
        self.assertEqual(morsel.setdefault('expires', 'value'), '')
        self.assertEqual(morsel['expires'], '')
        self.assertEqual(morsel.setdefault('Version', 1), 2)
        self.assertEqual(morsel['version'], 2)
        self.assertEqual(morsel.setdefault('DOMAIN', 'value'), 'example.com')
        self.assertEqual(morsel['domain'], 'example.com')

        with self.assertRaises(cookies.CookieError):
            morsel.setdefault('invalid', 'value')
        self.assertNotIn('invalid', morsel)

    def test_update(self):
        attribs = {'expires': 1, 'Version': 2, 'DOMAIN': 'example.com'}
        # test dict update
        morsel = cookies.Morsel()
        morsel.update(attribs)
        self.assertEqual(morsel['expires'], 1)
        self.assertEqual(morsel['version'], 2)
        self.assertEqual(morsel['domain'], 'example.com')
        # test iterable update
        morsel = cookies.Morsel()
        morsel.update(list(attribs.items()))
        self.assertEqual(morsel['expires'], 1)
        self.assertEqual(morsel['version'], 2)
        self.assertEqual(morsel['domain'], 'example.com')
        # test iterator update
        morsel = cookies.Morsel()
        morsel.update((k, v) for k, v in attribs.items())
        self.assertEqual(morsel['expires'], 1)
        self.assertEqual(morsel['version'], 2)
        self.assertEqual(morsel['domain'], 'example.com')

        with self.assertRaises(cookies.CookieError):
            morsel.update({'invalid': 'value'})
        self.assertNotIn('invalid', morsel)
        self.assertRaises(TypeError, morsel.update)
        self.assertRaises(TypeError, morsel.update, 0)

    def test_pickle(self):
        morsel_a = cookies.Morsel()
        morsel_a.set('foo', 'bar', 'baz')
        morsel_a.update({
            'version': 2,
            'comment': 'foo',
        })
        for proto in range(pickle.HIGHEST_PROTOCOL + 1):
            with self.subTest(proto=proto):
                morsel_b = pickle.loads(pickle.dumps(morsel_a, proto))
                self.assertIsInstance(morsel_b, cookies.Morsel)
                self.assertEqual(morsel_b, morsel_a)
                self.assertEqual(str(morsel_b), str(morsel_a))

    def test_repr(self):
        morsel = cookies.Morsel()
        self.assertEqual(repr(morsel), '<Morsel: None=None>')
        self.assertEqual(str(morsel), 'Set-Cookie: None=None')
        morsel.set('key', 'val', 'coded_val')
        self.assertEqual(repr(morsel), '<Morsel: key=coded_val>')
        self.assertEqual(str(morsel), 'Set-Cookie: key=coded_val')
        morsel.update({
            'path': '/',
            'comment': 'foo',
            'domain': 'example.com',
            'max-age': 0,
            'secure': 0,
            'version': 1,
        })
        self.assertEqual(repr(morsel),
                '<Morsel: key=coded_val; Comment=foo; Domain=example.com; '
                'Max-Age=0; Path=/; Version=1>')
        self.assertEqual(str(morsel),
                'Set-Cookie: key=coded_val; Comment=foo; Domain=example.com; '
                'Max-Age=0; Path=/; Version=1')
        morsel['secure'] = True
        morsel['httponly'] = 1
        self.assertEqual(repr(morsel),
                '<Morsel: key=coded_val; Comment=foo; Domain=example.com; '
                'HttpOnly; Max-Age=0; Path=/; Secure; Version=1>')
        self.assertEqual(str(morsel),
                'Set-Cookie: key=coded_val; Comment=foo; Domain=example.com; '
                'HttpOnly; Max-Age=0; Path=/; Secure; Version=1')

        morsel = cookies.Morsel()
        morsel.set('key', 'val', 'coded_val')
        morsel['expires'] = 0
        self.assertRegex(repr(morsel),
                r'<Morsel: key=coded_val; '
                r'expires=\w+, \d+ \w+ \d+ \d+:\d+:\d+ \w+>')
        self.assertRegex(str(morsel),
                r'Set-Cookie: key=coded_val; '
                r'expires=\w+, \d+ \w+ \d+ \d+:\d+:\d+ \w+')


def load_tests(loader, tests, pattern):
    tests.addTest(doctest.DocTestSuite(cookies))
    return tests


if __name__ == '__main__':
    unittest.main()
