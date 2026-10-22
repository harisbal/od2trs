//! Tours on a layered graph. No dependencies.
//! usage: tours_rs toy_od.csv A Home,Work,Other,Work,Home

use std::collections::HashMap;
use std::{env, fs};

fn purpose_of(a: &str, b: &str) -> String {
    if a == "Home" || b == "Home" {
        let other = if a == "Home" { b } else { a };
        format!("HB{}", &other[..1])
    } else if a == "Work" || b == "Work" {
        "NHBW".into()
    } else {
        "NHBO".into()
    }
}

/// The edges of one leg in CSR form: those leaving zone z are start[z]..start[z + 1].
struct Leg {
    start: Vec<usize>,
    orig: Vec<usize>,
    dest: Vec<usize>,
    trips: Vec<f64>,
}

impl Leg {
    fn edges(&self, z: usize) -> std::ops::Range<usize> {
        self.start[z]..self.start[z + 1]
    }
}

fn build_legs(od: &[[String; 5]], zone: &HashMap<String, usize>, n_zones: usize, acts: &[&str], home: usize) -> Vec<Leg> {
    let n = acts.len() - 1;
    (0..n)
        .map(|i| {
            let (purpose, direction) = (
                purpose_of(acts[i], acts[i + 1]),
                if i == 0 { "FromHome" } else if i == n - 1 { "ToHome" } else { "NonHome" },
            );
            // [orig, dest, purpose, direction, trips]; leg 0 leaves from the home zone only
            let mut rows: Vec<(usize, usize, f64)> = od
                .iter()
                .filter(|r| r[2] == purpose && r[3] == direction && (i > 0 || zone[&r[0]] == home))
                .map(|r| (zone[&r[0]], zone[&r[1]], r[4].parse().unwrap()))
                .collect();
            rows.sort_by_key(|r| r.0);
            let mut start = vec![0; n_zones + 1];
            for r in &rows {
                start[r.0 + 1] += 1;
            }
            for z in 0..n_zones {
                start[z + 1] += start[z];
            }
            Leg {
                start,
                orig: rows.iter().map(|r| r.0).collect(),
                dest: rows.iter().map(|r| r.1).collect(),
                trips: rows.iter().map(|r| r.2).collect(),
            }
        })
        .collect()
}

/// keep[i][z]: node (i, z) is reachable from home and can still get home.
fn trim(legs: &[Leg], n_zones: usize, home: usize) -> Vec<Vec<bool>> {
    let n = legs.len();
    let mut fwd = vec![vec![false; n_zones]; n + 1];
    let mut bwd = vec![vec![false; n_zones]; n + 1];
    fwd[0][home] = true;
    bwd[n][home] = true;
    for i in 0..n {
        for e in 0..legs[i].orig.len() {
            if fwd[i][legs[i].orig[e]] {
                fwd[i + 1][legs[i].dest[e]] = true;
            }
        }
    }
    for i in (0..n).rev() {
        for e in 0..legs[i].orig.len() {
            if bwd[i + 1][legs[i].dest[e]] {
                bwd[i][legs[i].orig[e]] = true;
            }
        }
    }
    (0..=n).map(|i| (0..n_zones).map(|z| fwd[i][z] && bwd[i][z]).collect()).collect()
}

fn count_tours(legs: &[Leg], keep: &[Vec<bool>], n_zones: usize, home: usize) -> u64 {
    let mut paths = vec![0u64; n_zones];
    paths[home] = 1;
    for (i, leg) in legs.iter().enumerate() {
        let mut next = vec![0u64; n_zones];
        for e in 0..leg.orig.len() {
            if keep[i][leg.orig[e]] && keep[i + 1][leg.dest[e]] {
                next[leg.dest[e]] += paths[leg.orig[e]];
            }
        }
        paths = next;
    }
    paths[home]
}

/// beta[i][z]: probability of getting home in the remaining legs, from zone z at layer i.
fn completion(legs: &[Leg], n_zones: usize, home: usize) -> Vec<Vec<f64>> {
    let n = legs.len();
    let mut beta = vec![vec![0.0; n_zones]; n + 1];
    beta[n][home] = 1.0;
    for i in (0..n).rev() {
        for z in 0..n_zones {
            let r = legs[i].edges(z);
            let total: f64 = legs[i].trips[r.clone()].iter().sum();
            if total > 0.0 {
                beta[i][z] = r.map(|e| legs[i].trips[e] * beta[i + 1][legs[i].dest[e]]).sum::<f64>() / total;
            }
        }
    }
    beta
}

fn list_tours(legs: &[Leg], keep: &[Vec<bool>], path: &mut Vec<usize>, out: &mut Vec<Vec<usize>>) {
    let i = path.len() - 1;
    if i == legs.len() {
        out.push(path.clone());
        return;
    }
    let z = path[i];
    for e in legs[i].edges(z) {
        if keep[i + 1][legs[i].dest[e]] {
            path.push(legs[i].dest[e]);
            list_tours(legs, keep, path, out);
            path.pop();
        }
    }
}

fn tour_probability(legs: &[Leg], path: &[usize], beta0: f64) -> f64 {
    let mut p = 1.0;
    for (i, w) in path.windows(2).enumerate() {
        let r = legs[i].edges(w[0]);
        let total: f64 = legs[i].trips[r.clone()].iter().sum();
        let e = r.clone().find(|&e| legs[i].dest[e] == w[1]).unwrap();
        p *= legs[i].trips[e] / total;
    }
    p / beta0
}

struct Rng(u64); // xorshift64
impl Rng {
    fn uniform(&mut self) -> f64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 11) as f64 / (1u64 << 53) as f64
    }
}

/// Each edge is picked with probability proportional to trips * beta(next).
fn sample_tour(legs: &[Leg], beta: &[Vec<f64>], home: usize, rng: &mut Rng) -> Vec<usize> {
    let mut path = vec![home];
    for (i, leg) in legs.iter().enumerate() {
        let r = leg.edges(path[i]);
        let w: Vec<f64> = r.clone().map(|e| leg.trips[e] * beta[i + 1][leg.dest[e]]).collect();
        let mut x = rng.uniform() * w.iter().sum::<f64>();
        let pick = w.iter().position(|&v| { x -= v; x < 0.0 }).unwrap_or(w.len() - 1);
        path.push(leg.dest[r.start + pick]);
    }
    path
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let text = fs::read_to_string(&args[1]).unwrap();
    let od: Vec<[String; 5]> = text
        .lines()
        .skip(1)
        .map(|l| {
            let f: Vec<&str> = l.split(',').collect();
            [f[0], f[1], f[2], f[3], f[4]].map(String::from)
        })
        .collect();
    let mut names: Vec<String> = od.iter().flat_map(|r| [r[0].clone(), r[1].clone()]).collect();
    names.sort();
    names.dedup();
    let zone: HashMap<String, usize> = names.iter().cloned().zip(0..).collect();
    let (n_zones, home) = (names.len(), zone[&args[2]]);
    let acts: Vec<&str> = args[3].split(',').collect();

    let legs = build_legs(&od, &zone, n_zones, &acts, home);
    let keep = trim(&legs, n_zones, home);
    let beta = completion(&legs, n_zones, home);
    let label = |p: &[usize]| p.iter().map(|&z| names[z].as_str()).collect::<Vec<_>>().join(" ");

    println!("tours {} edges {}", count_tours(&legs, &keep, n_zones, home), {
        let mut edges = 0;
        for (i, leg) in legs.iter().enumerate() {
            edges += (0..leg.orig.len()).filter(|&e| keep[i][leg.orig[e]] && keep[i + 1][leg.dest[e]]).count();
        }
        edges
    });
    println!("beta0 {:.4}", beta[0][home]);
    let mut tours = Vec::new();
    list_tours(&legs, &keep, &mut vec![home], &mut tours);
    let mut ranked: Vec<(f64, &Vec<usize>)> = tours.iter().map(|t| (tour_probability(&legs, t, beta[0][home]), t)).collect();
    ranked.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
    for (p, t) in &ranked {
        println!("{} {:.4}", label(t), p);
    }
    let mut rng = Rng(88172645463325252);
    let mut seen: HashMap<String, usize> = HashMap::new();
    for _ in 0..20000 {
        *seen.entry(label(&sample_tour(&legs, &beta, home, &mut rng))).or_default() += 1;
    }
    let mut seen: Vec<_> = seen.into_iter().collect();
    seen.sort();
    println!("sampled {}", seen.iter().map(|(k, v)| format!("{k}: {:.3}", *v as f64 / 20000.0)).collect::<Vec<_>>().join(", "));
}
