import torch

from torch.optim.optimizer import Optimizer

from Line_Search import Armijo
from Line_Search import Wolfe
from Line_Search import Strong_Wolfe

import copy

import warnings

__all__ = ('FR',)

class FR(Optimizer):
    r"""Implements Fletcher-Reeves Conjugate Gradient.

    Arguments:
        params: iterable of parameters to optimize or dicts defining
            parameter groups
        eps: term added to the denominator to improve
            numerical stability (default: 1e-3)
        line_search: designates line search to use (default: 'Armijo')
            Options:
                'None': uses exact line search(requires the loss is quadratic)
                'Armijo': uses Armijo line search
                'Wolfe': uses Wolfe line search
                'Strong_Wolfe': uses Strong_Wolfe line search
        c1: sufficient decrease constant in (0, 1) (default: 1e-4)
        c2: curvature condition constant in (0, 1) (default: 0.1)
        lr: initial step length of Line Search (default: 1)
        rho: contraction factor of Line Search (default: 0.5)
        eta: adjustment factor of Wolfe Line Search's step (default: 5)
        amax: maximum step length of Strong Wolfe Line Search (default: 0.6)
        max_ls: maximum number of line search steps permitted (default: 10)
    
    Example:
        >>> import ncg_optimizer as optim
        >>> optimizer = optim.FR(
        >>>     model.parameters(), eps = 1e-3, 
        >>>     line_search = 'Armijo', c1 = 1e-4, c2 = 0.4,
        >>>     lr = 1, rho = 0.5, eta = 0.5, amax = 0.6, max_ls = 10)
        >>> def closure():
        >>>     optimizer.zero_grad()
        >>>     loss_fn(model(input), target).backward()
        >>>     return loss_fn
        >>> optimizer.step(closure)
    """

    def __init__(
        self,
        params,
        eps = 1e-3,
        line_search = 'Armijo',
        c1 = 1e-4,
        c2 = 0.4,
        lr = 1,
        rho = 0.5,
        eta = 5,
        amax = 0.6,
        max_ls = 10,
    ):
        if eps < 0.0:
            raise ValueError('Invalid epsilon value: {}'.format(eps))

        if line_search not in [
            'Armijo',
            'Wolfe',
            'Strong_Wolfe', 
            'None',
            ]:
            raise ValueError("Invalid line search: {}".format(line_search))
        elif line_search == 'None':
            warnings.warn("Unless loss is a quadratic function, this is not correct")

        if not (0.0 < c1 < 0.5):
            raise ValueError('Invalid c1 value: {}'.format(c1))

        if not (c1 < c2 < 1.0):
            raise ValueError('Invalid c2 value: {}'.format(c2))

        if lr < 0.0:
            raise ValueError('Invalid lr value: {}'.format(lr))

        if not (0.0 < rho < 1.0):
            raise ValueError('Invalid rho value: {}'.format(rho))

        if not (1.0 < eta):
            raise ValueError('Invalid eta value: {}'.format(eta))
        
        if not (0.0 < amax):
            raise ValueError('Invalid amax value: {}'.format(amax))

        if max_ls % 1 != 0 or max_ls <= 0:
            raise ValueError('Invalid max_ls value: {}'.format(max_ls))

        defaults = dict(
            eps=eps,
            line_search=line_search,
            c1 = c1,
            c2 = c2,
            lr = lr,
            rho = rho,
            eta = eta,
            amax = amax,
            max_ls = max_ls,
        )

        super(FR, self).__init__(params, defaults)

    def _get_A(p, d_p):
        A = torch.stack(
                        [torch.autograd.grad(
                            d_p[i],
                            p, 
                            grad_outputs=torch.ones_like(d_p[i]),
                            retain_graph=True)[0]
                        for i in range(0, len(d_p))])
        
        return A

    def Exact(A, d_p, d):
        rdotr = torch.dot(-d, d_p.data)

        z = torch.matmul(A, d)

        alpha = rdotr / torch.matmul(d, z)

        return alpha

    def step(self, closure=None):
        r"""Performs a single optimization step (parameter update).

        Arguments:
            closure (callable): A closure that reevaluates the model and
            returns the loss. Optional for most optimizers.

        .. note::
            Unless otherwise specified, this function should not modify the
            ``.grad`` field of the parameters.
        """

        loss = None
        if closure is not None:
            with torch.enable_grad():
                loss = closure()

        for group in self.param_groups:
            for p in group['params']:
                if p.grad is None:
                    continue
                
                d_p = p.grad

                state = self.state[p]

                if len(state) == 0:
                    # Grade of quadratic functions
                    state['g'] = copy.deepcopy(d_p.data)

                    if torch.norm(state['g']) < group['eps']:
                        # Stop condition
                        return loss

                    # Direction vector
                    state['d'] = copy.deepcopy(-d_p.data)

                    # Determine whether to calculate A
                    state['index'] = True
                    
                    # Step of Conjugate Gradient
                    state['step'] = 0
                else:
                    # Parameters that make gradient steps
                    state['beta'] = torch.norm(d_p.data) / torch.norm(state['g'])

                    state['g'] = copy.deepcopy(d_p.data)

                    if torch.norm(state['g']) < group['eps']:
                        return loss
                    
                    state['d'] = -state['g'] + state['beta'] * state['d']

                    state['index'] = False

                line_search = group['line_search']
                c1 = group['c1']
                c2 = group['c2']
                lr = group['lr']
                rho = group['rho']
                eta = group['eta']
                amax = group['amax']
                max_ls = group['max_ls']

                if line_search == 'None':
                    if state['index']:
                        state['A'] = FR._get_A(p, d_p)
                        alpha = FR.Exact(state['A'], d_p, state['d'])
                    else:
                        alpha = FR.Exact(state['A'], d_p, state['d'])

                elif line_search == 'Armijo':
                    alpha = Armijo(closure, p, state['g'], state['d'], lr, rho, c1, max_ls)

                elif line_search == 'Wolfe':
                    k = state['step']
                    alpha = Wolfe(closure, p, d_p, state['d'], lr, c1, c2, eta, k, max_ls)
                    state['step'] = state['step'] + 1
                
                elif line_search == 'Strong_Wolfe':
                    alpha = Strong_Wolfe(closure, p, d_p, state['d'], lr, c1, c2, amax, max_ls)
                
                p.data.add_(state['d'], alpha=alpha)

        return loss