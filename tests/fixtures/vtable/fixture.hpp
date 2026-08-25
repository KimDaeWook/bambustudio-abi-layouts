#pragma once

struct VtableFixture {
    virtual ~VtableFixture() = default;
    virtual int alpha() const = 0;
    virtual void beta(int) = 0;
};
