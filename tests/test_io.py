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


def test_intrazonal_cells_are_dropped_unless_kept(tmp_path):
    (tmp_path / "od.csv").write_text(
        "Orig,Dest,Timeperiod,Purpose,Direction,Trips\n"
        "A,B,AM,HBW,FromHome,3\n"
        "B,B,AM,NHBW,NonHomeBased,2\n"
    )
    dropped = io.read_od(tmp_path / "od.csv", 1, {}, ["AM"])
    kept = io.read_od(tmp_path / "od.csv", 1, {}, ["AM"], keep_intrazonal=True)

    assert dropped.index.get_level_values("Orig").tolist() == ["A"]
    assert kept.index.get_level_values("Orig").tolist() == ["A", "B"]
    # Odpairids are assigned before the filters, so they agree
    assert kept["Odpairid"].tolist() == [0, 1]
    assert dropped["Odpairid"].tolist() == [0]
