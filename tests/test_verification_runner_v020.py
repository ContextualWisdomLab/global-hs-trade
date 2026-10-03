from pathlib import Path
import runpy


def test_verification_runner_isolates_unrelated_plugins_without_hiding_warnings():
    path=Path(__file__).resolve().parents[1]/'scripts/check.py'
    assert path.is_file()
    namespace=runpy.run_path(str(path))
    result=namespace['test_environment']({'PYTEST_ADDOPTS':'--maxfail=1','PYTEST_PLUGINS':'external.plugin','X':'kept'})
    assert result['PYTEST_DISABLE_PLUGIN_AUTOLOAD']=='1'
    assert result['PYTHONWARNINGS']=='error'
    assert 'PYTEST_ADDOPTS' not in result and 'PYTEST_PLUGINS' not in result
    assert result['X']=='kept'
