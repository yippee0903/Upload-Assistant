from src.takescreens import par_scale_factors


def test_par_scale_factors():
    assert par_scale_factors(1.0, 16 / 9, 1920, 1080) == (1.0, 1.0)
    w, h = par_scale_factors(1.422, 16 / 9, 720, 576)
    assert (w, h) == (1.422, 1.0)
    w, h = par_scale_factors(0.9, 4 / 3, 720, 480)
    assert w == 1.0 and abs(h - 720 / (4 / 3 * 480)) < 1e-9
