from tests.helpers import mod

def test_worldwide_country_catalog_not_korea_only():
    countries=mod('coverage.catalog').countries()
    assert all(c in countries for c in ['BR','DE','US','CN','IN','ZA','VN','GB','KR'])
    assert len(countries)>=240

def test_germany_not_falsely_marked_as_connected():
    result=mod('coverage.catalog').coverage_for('DE','X','value')
    assert result['company_values_live_connected'] is False
    assert 'national_aggregate' in {r['kind'] for r in result['routes']}

def test_uk_presence_not_full_values():
    result=mod('coverage.catalog').coverage_for('GB','M','value')
    route=next(r for r in result['routes'] if r['source_identifier']=='hmrc-traders')
    assert route['has_company_value'] is False
