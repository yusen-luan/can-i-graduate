# Iteration 1 prerequisite graph

Generated from `data/modules.yaml`.

- Solid arrow: ordinary prerequisite
- Dashed arrow: conditional / bridging prerequisite
- Dotted bidirectional edge: corequisite
- Generic GE/ID/CD nodes are placeholders, not specific real modules

```mermaid
flowchart LR
    subgraph math_bridging["Math bridging"]
        MA1301(["MA1301"])
        MA1301X(["MA1301X"])
    end
    subgraph english_bridging["English bridging"]
        ES1000(["ES1000"])
        ES1103(["ES1103"])
    end
    subgraph cs_foundation["CS foundation"]
        CS1101S["CS1101S"]
        CS1231S["CS1231S"]
        CS2030S["CS2030S"]
        CS2040S["CS2040S"]
        CS2100["CS2100"]
        CS2101["CS2101"]
        CS2103T["CS2103T"]
        CS2106["CS2106"]
        CS2109S["CS2109S"]
        CS3230["CS3230"]
    end
    subgraph math_statistics["Mathematics & statistics"]
        MA1521["MA1521"]
        MA1522["MA1522"]
        ST2334["ST2334"]
    end
    subgraph university_level_requirements["University-level requirements"]
        ES2660["ES2660"]
        GEA1000["GEA1000"]
        GEC_GENERIC{{"GEC_GENERIC"}}
        GES_GENERIC{{"GES_GENERIC"}}
        GEN_GENERIC{{"GEN_GENERIC"}}
    end
    subgraph computing_ethics["Computing ethics"]
        IS1108["IS1108"]
    end
    subgraph interdisciplinary_cross_disciplinary["Interdisciplinary / cross-disciplinary"]
        ID_GENERIC_1{{"ID_GENERIC_1"}}
        ID_GENERIC_2{{"ID_GENERIC_2"}}
        ID_GENERIC_3{{"ID_GENERIC_3"}}
        CD_GENERIC_1{{"CD_GENERIC_1"}}
    end
    CS1101S --> CS2030S
    CS1101S --> CS2040S
    CS1231S --> CS2040S
    MA1521 --> ST2334
    CS1101S --> CS2100
    CS2030S --> CS2103T
    CS2040S --> CS2103T
    CS2100 --> CS2106
    MA1521 --> CS2109S
    CS2040S --> CS2109S
    CS2040S --> CS3230
    COND_1{"MA1301 OR MA1301X"}
    MA1301 -. "one of" .-> COND_1
    MA1301X -. "one of" .-> COND_1
    COND_1 -. "needs_math_bridging=true" .-> CS1231S
    COND_2{"MA1301 OR MA1301X"}
    MA1301 -. "one of" .-> COND_2
    MA1301X -. "one of" .-> COND_2
    COND_2 -. "needs_math_bridging=true" .-> MA1521
    COND_3{"MA1301 OR MA1301X"}
    MA1301 -. "one of" .-> COND_3
    MA1301X -. "one of" .-> COND_3
    COND_3 -. "needs_math_bridging=true" .-> MA1522
    ES1103 -. "english_path in [es1103_required,es1000_then_es1103]" .-> ES2660
    ES1000 -. "english_path=es1000_then_es1103" .-> ES1103
    CS2101 == "8-unit bundle / same semester" ==> CS2103T
```

## Current conditional pathways

- Math bridging: if `needs_math_bridging=true`, satisfy MA1301 or MA1301X before MA1521, MA1522, and CS1231S.
- English baseline: `english_path=direct_es2660` adds no English bridge.
- English path `es1103_required`: ES1103 must be satisfied before ES2660.
- English path `es1000_then_es1103`: ES1000 -> ES1103 -> ES2660.
