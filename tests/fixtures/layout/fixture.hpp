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

struct VtableFixture {
    virtual ~VtableFixture() = default;
    virtual int alpha() const = 0;
    virtual void beta(int) = 0;
};
