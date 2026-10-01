# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Concrete test-suite adapters: upstream's registry, loading the adapters shipped here.

Every task carries this same file; a suite type whose module the task does not ship is
left out of `SUITE_TYPES`.
"""

from importlib import import_module
from importlib.util import find_spec

_TABLE = {
    "agda-tasty": ("agda_tasty", "AgdaTastySuite"),
    "bazel": ("bazel", "BazelSuite"),
    "boost-functional": ("boost_functional", "BoostFunctionalSuite"),
    "boost-test": ("boost_test", "BoostTestSuite"),
    "botan-test": ("botan_test", "BotanTestSuite"),
    "cargo": ("cargo", "CargoSuite"),
    "cargo-flat-snapshot": ("cargo_flat_snapshot", "CargoFlatSnapshotSuite"),
    "cargo-reffile": ("cargo_reffile", "CargoRefFileSuite"),
    "cargo-snapshot": ("cargo_snapshot", "CargoSnapshotSuite"),
    "cargo-sqllogic": ("cargo_sqllogic", "CargoSqlLogicSuite"),
    "cargo-unit": ("cargo_unit", "CargoUnitSuite"),
    "clippy-ui": ("clippy_ui", "ClippyUiSuite"),
    "clojure-hawk": ("clojure_hawk", "ClojureHawkSuite"),
    "compiletest": ("compiletest", "CompiletestSuite"),
    "cppcheck-testrunner": ("cppcheck_testrunner", "CppcheckTestrunnerSuite"),
    "crystal-spec": ("crystal_spec", "CrystalSpecSuite"),
    "ctest": ("ctest", "CTestSuite"),
    "ctest-data": ("ctest_data", "CTestDataSuite"),
    "ctest-dir-prefixed": ("ctest_dir_prefixed", "CTestDirPrefixedSuite"),
    "ctest-monolithic": ("ctest_monolithic", "CTestMonolithicSuite"),
    "ctest-path": ("ctest_path", "CTestPathSuite"),
    "ctest-path-map": ("ctest_path_map", "CTestPathMapSuite"),
    "ctest-path-names": ("ctest_path_names", "CTestPathNamesSuite"),
    "ctest-per-project": ("ctest_per_project", "CTestPerProjectSuite"),
    "ctest-source-owner": ("ctest_source_owner", "CTestSourceOwnerSuite"),
    "ctest-target": ("ctest_target", "CTestTargetSuite"),
    "curl-runtests": ("curl_runtests", "CurlRuntestsSuite"),
    "dart-file": ("dart_file", "DartFileSuite"),
    "dmd-testsuite": ("dmd_testsuite", "DmdTestsuiteSuite"),
    "doctest": ("doctest", "DoctestSuite"),
    "dotnet-test": ("dotnet_test", "DotnetTestSuite"),
    "duckdb-unittest": ("duckdb_unittest", "DuckdbUnittestSuite"),
    "dune": ("dune_runtest", "DuneSuite"),
    "emscripten-runner": ("emscripten_runner", "EmscriptenRunnerSuite"),
    "eunit-rebar": ("eunit_rebar", "EunitRebarSuite"),
    "exunit": ("exunit", "ExUnitSuite"),
    "flint-module-main": ("flint_module_main", "FlintModuleMainSuite"),
    "gie": ("gie", "GieSuite"),
    "go": ("go", "GoSuite"),
    "gradle": ("gradle", "GradleSuite"),
    "gtest": ("gtest", "GTestSuite"),
    "gtest-yaml": ("yaml_gtest", "YamlGTestSuite"),
    "idris-golden": ("idris_golden", "IdrisGoldenSuite"),
    "jerry": ("jerry", "JerrySuite"),
    "jest": ("jest", "JestSuite"),
    "jest-corpus": ("jest_corpus", "JestCorpusSuite"),
    "jest-fixture": ("jest_fixture", "JestFixtureSuite"),
    "jest-per-package": ("jest_per_package", "JestPerPackageSuite"),
    "jest-vitest": ("jest_vitest", "JestVitestSuite"),
    "julia": ("julia", "JuliaSuite"),
    "julia-base": ("julia_base", "JuliaBaseSuite"),
    "julia-eval": ("julia_evaluation", "JuliaEvaluationSuite"),
    "julia-safetestset": ("julia_safetestset", "JuliaSafeTestsetSuite"),
    "julia-safetestset-eval": ("julia_safetestset_evaluation", "JuliaSafeTestsetEvaluationSuite"),
    "kokkos-gtest": ("kokkos_gtest", "KokkosGTestSuite"),
    "lake-module": ("lake_module", "LakeModuleSuite"),
    "lean-ctest": ("lean_ctest", "LeanCTestSuite"),
    "lit": ("lit", "LitSuite"),
    "llvm-lit": ("llvm_lit", "LlvmLitSuite"),
    "maven": ("maven", "MavenSuite"),
    "meson": ("meson", "MesonSuite"),
    "meson-project-test": ("meson_project_test", "MesonProjectTestSuite"),
    "micropython-run-tests": ("micropython_run_tests", "MicropythonRunTestsSuite"),
    "minitest": ("minitest", "MinitestSuite"),
    "mocha": ("mocha", "MochaSuite"),
    "mocha-fixture": ("mocha_fixture", "MochaFixtureSuite"),
    "netlib-tester": ("netlib_tester", "NetlibTesterSuite"),
    "pandoc-tasty": ("pandoc_tasty", "PandocTastySuite"),
    "perl-core": ("perl_core", "PerlCoreSuite"),
    "phpt": ("phpt", "PhptSuite"),
    "phpunit": ("phpunit", "PhpUnitSuite"),
    "prove": ("prove", "ProveSuite"),
    "pytest": ("pytest", "PytestSuite"),
    "pytest-corpus": ("pytest_corpus", "PytestCorpusSuite"),
    "pytest-eval": ("pytest_evaluation", "PytestEvaluationSuite"),
    "pytest-inline-case": ("pytest_inline_case", "PytestInlineCaseSuite"),
    "qunit": ("qunit", "QUnitSuite"),
    "r-testdatatable": ("r_testdatatable", "RTestDataTableSuite"),
    "redis-tcl": ("redis_tcl", "RedisTclSuite"),
    "regrtest": ("regrtest", "RegrtestSuite"),
    "repro-eval": ("reproduction_evaluation", "ReproductionEvaluationSuite"),
    "rocq-testsuite": ("rocq_testsuite", "RocqTestSuite"),
    "rspec": ("rspec", "RSpecSuite"),
    "ruby-testunit": ("ruby_testunit", "RubyTestUnitSuite"),
    "sbt-vulpix": ("sbt_vulpix", "SbtVulpixSuite"),
    "sbt-vulpix-eval": ("sbt_vulpix_evaluation", "SbtVulpixEvaluationSuite"),
    "tarantool-test-run": ("tarantool_test_run", "TarantoolTestRunSuite"),
    "terser-compress": ("terser_compress", "TerserCompressSuite"),
    "testament": ("testament", "TestamentSuite"),
    "union": ("union", "UnionSuite"),
    "v": ("v_lang", "VSuite"),
    "vitest": ("vitest", "VitestSuite"),
    "z3-unit": ("z3_unit", "Z3UnitSuite"),
    "zig": ("zig", "ZigSuite"),
    "zig-eval": ("zig_evaluation", "ZigEvaluationSuite"),
}

SUITE_TYPES = {
    name: getattr(import_module(f".{module}", __name__), cls)
    for name, (module, cls) in _TABLE.items()
    if find_spec(f"{__name__}.{module}") is not None
}
