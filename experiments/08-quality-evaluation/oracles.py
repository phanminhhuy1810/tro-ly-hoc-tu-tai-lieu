"""Trusted fixture arithmetic; never execute model text or use its key as gold."""
from fractions import Fraction
import ipaddress
import math


def polynomial_integral(coefficients, bounds):
    a,b=map(Fraction,bounds)
    return sum((Fraction(c,p+1)*(b**(p+1)-a**(p+1))
                for p,c in enumerate(coefficients)),Fraction(0))


def verify_facts(facts):
    kind=facts['oracle']
    if kind=='ipv4':
        n=ipaddress.ip_interface(facts['input']).network
        if n.prefixlen>=31:raise ValueError('This fixture uses conventional subnet endpoints, not /31 or /32.')
        return {'verification':'computed','network':str(n.network_address),'broadcast':str(n.broadcast_address),
                'first_host':str(n.network_address+1),'last_host':str(n.broadcast_address-1),
                'mask':str(n.netmask),'host_bits':32-n.prefixlen,'total_addresses':n.num_addresses,
                'usable_hosts':n.num_addresses-2}
    if kind=='ipv6':
        a=ipaddress.ip_address(facts['input'])
        assert a.version==6 and a.max_prefixlen==facts['bits']
        assert len(a.exploded.split(':'))==facts['groups']
        assert ipaddress.ip_address(facts['loopback']).is_loopback
        assert ipaddress.ip_address(facts['unspecified']).is_unspecified
        return {'verification':'computed','compressed':a.compressed,'expanded':a.exploded,'bits':a.max_prefixlen}
    if kind=='longest_prefix':
        routes=[(ipaddress.ip_network(net),hop) for net,hop in facts['routes']]
        found={}
        for address,wanted in facts['destinations'].items():
            a=ipaddress.ip_address(address)
            hop=max(((net.prefixlen,hop) for net,hop in routes if a in net),key=lambda v:v[0])[1]
            assert hop==wanted;found[address]=hop
        return {'verification':'computed','selected_routes':found}
    if kind=='polynomial_integral':
        value=polynomial_integral(facts['coefficients'],facts['bounds'])
        second=polynomial_integral(facts['second_coefficients'],facts['second_bounds'])
        assert value==Fraction(facts['result']) and -value==Fraction(facts['reversed'])
        assert second==Fraction(facts['second_result'])
        return {'verification':'computed','integral':str(value),'reversed':str(-value),'second_integral':str(second)}
    if kind=='chain_power':
        coefficient=facts['power']*facts['inner_slope']
        value=coefficient*(facts['inner_slope']*facts['at']+facts['inner_intercept'])**(facts['power']-1)
        assert coefficient==facts['coefficient'] and value==facts['value_at']
        return {'verification':'computed','coefficient':coefficient,'value_at':value}
    if kind=='parts_exp':
        a,b=facts['bounds'];antiderivative=lambda x:(x-1)*math.exp(x)
        upper,lower=antiderivative(b),antiderivative(a)
        # Product rule: (1 + (x-1))*exp(x) = x*exp(x).
        assert math.isclose(upper,facts['upper_value']) and math.isclose(lower,facts['lower_value'])
        assert math.isclose(upper-lower,facts['result'])
        return {'verification':'computed','upper_value':upper,'lower_value':lower,'integral':upper-lower,
                'identity':'d((x-1)*exp(x))/dx = (1+x-1)*exp(x) = x*exp(x)'}
    if kind=='partial_polynomial':
        x,y=facts['point'];dx=dy=0
        for c,px,py in facts['terms']:
            if px:dx+=c*px*x**(px-1)*y**py
            if py:dy+=c*py*x**px*y**(py-1)
        assert dx==facts['dx'] and dy==facts['dy']
        return {'verification':'computed','dx_at_point':dx,'dy_at_point':dy}
    if kind=='concept_table':
        return {'verification':'agent_source_crosscheck_only_needs_independent_review',
                'limit':'A deterministic computation cannot establish these psychology labels; no automatic factual pass.'}
    raise ValueError('Unknown fixture oracle')
