from od2trs import io


def test_csv_zone_ids_keep_leading_zeros(tmp_path):
    (tmp_path / "od.csv").write_text(
        "Orig,Dest,Timeperiod,Purpose,Direction,Trips\n010111,020202,AM,HBW,FromHome,3\n"
    )
    (tmp_path / "costs.csv").write_text("Orig,Dest,Distance\n010111,020202,1500\n")
    (tmp_path / "zones.csv").write_text("Zone,X,Y\n010111,1.0,2.0\n")

    od = io.read_od(tmp_path / "od.csv", 1, {}, ["AM"])
    costs = io.read_costs(tmp_path / "costs.csv")
    zones = io.read_zones_info(tmp_path / "zones.csv")

    assert od.join(costs)["Distance"].tolist() == [1500.0]
    assert od["Trips"].tolist() == [3]
    assert zones.index.tolist() == ["010111"]
    assert zones["Coords"].tolist() == [(1.0, 2.0)]
