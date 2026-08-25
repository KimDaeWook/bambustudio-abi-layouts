#pragma once

struct FixtureBase {
    int base_value;
};

struct FixtureProbe : FixtureBase {
private:
    bool enabled;
    double ratio;
    char marker[3];
};
