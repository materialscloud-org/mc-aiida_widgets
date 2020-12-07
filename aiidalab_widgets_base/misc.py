"""Some useful classes used acrross the repository."""

import ipywidgets as ipw
from traitlets import Unicode


class CopyToClipboardButton(ipw.Button):
    """Button to copy text to clipboard."""

    value = Unicode(allow_none=True)  # Traitlet that contains a string to copy.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        super().on_click(self.copy_to_clipboard)

    def copy_to_clipboard(self, change=None):  # pylint:disable=unused-argument
        """Copy text to clipboard."""
        from IPython.display import Javascript, display
        javas = Javascript("""
           function copyStringToClipboard (str) {{
               // Create new element
               var el = document.createElement('textarea');
               // Set value (string to be copied)
               el.value = str;
               // Set non-editable to avoid focus and move outside of view
               el.setAttribute('readonly', '');
               el.style = {{position: 'absolute', left: '-9999px'}};
               document.body.appendChild(el);
               // Select text inside element
               el.select();
               // Copy text to clipboard
               document.execCommand('copy');
               // Remove temporary element
               document.body.removeChild(el);
            }}
            copyStringToClipboard("{selection}");
       """.format(selection=self.value))  # For the moment works for Chrome, but doesn't work for Firefox.
        if self.value:  # If no value provided - do nothing.
            display(javas)


class ReversePolishNotation:
    """Class defining operations for RPN conversion"""

    #adapted from:
    # Author: Alaa Awad
    # Description: program converts infix to postfix notation
    #https://gist.github.com/awadalaa/7ef7dc7e41edb501d44d1ba41cbf0dc6
    def __init__(self, operators, operands=None):
        self.operands = operands
        self.operators = operators

    def haslessorequalpriority(self, opa, opb):
        """Priority of the different operators"""
        if opa not in self.operators:
            return False
        if opb not in self.operators:
            return False
        return self.operators[opa]['priority'] <= self.operators[opb]['priority']

    def isoperator(self, opx):
        """Identifies operators"""
        return opx in self.operators

    def isoperand(self, operator):
        """Identifies operands"""
        return operator not in set(self.operators.keys()).union({'(', ')'})

    @staticmethod
    def isopenparenthesis(operator):
        """Identifies open paretheses."""
        return operator == '('

    @staticmethod
    def iscloseparenthesis(operator):
        """Identifies closed paretheses."""
        return operator == ')'

    def convert(self, expr):
        """Convert expression to postfix."""
        stack = []
        output = []
        for char in expr:
            if self.isoperand(char):
                output.append(char)
            else:
                if self.isopenparenthesis(char):
                    stack.append(char)
                elif self.iscloseparenthesis(char):
                    operator = stack.pop()
                    while not self.isopenparenthesis(operator):
                        output.append(operator)
                        operator = stack.pop()
                else:
                    while stack and self.haslessorequalpriority(char, stack[-1]):
                        output.append(stack.pop())
                    stack.append(char)

        while stack:
            output.append(stack.pop())
        return output

    def parse_infix_notation(self, condition):
        """Convert a string containing the expression into a list of operators and operands."""
        # Do not modify the order of execution of the following replacements.
        condition = condition.replace(" ", "")
        condition = condition.replace(">=", "ge")  # operator = {operator} {d_from_adf_adf}
        condition = condition.replace("<=", "le")
        condition = condition.replace("!=", "ne")
        condition = condition.replace("=", "eq")
        condition = condition.replace("is", "")
        condition = condition.replace("in", "")
        condition = condition.replace('[', '_')
        condition = condition.replace(']', '_')
        condition = condition.replace(',', '_')
        for item in [
                'x', 'y', 'z', 'and', 'or', 'is', 'not', 'in', 'id', 'd_from', '>', '<', 'name', '+', '-', '*', '/',
                '^', 'ge', 'le', 'eq', 'ne', '(', ')'
        ]:
            condition = condition.replace(item, ' ' + item + ' ')

        csp = condition.split()
        clean = {'ge': '>=', 'le': '<=', 'eq': '=', 'ne': '!='}

        #changing order would brake conversion of 'name not [N,O]'
        specials = ['not', 'name', 'd_from']
        for spec in specials:
            while spec in csp:
                ind = csp.index(spec)
                csp[ind] = (spec + csp[ind + 1]).replace(" ", "")
                csp[ind + 1] = ''

        for key in clean:
            while key in csp:
                ind = csp.index(key)
                csp[ind] = clean[key]

        csp = list(filter(bool, csp))
        return csp

    def execute(self, expression):
        """Execute the provided expression."""

        def is_number(string):
            """Check if string is a number. """
            try:
                float(string)
                return True
            except ValueError:
                return False

        stack = []
        stackposition = -1
        infix_expression = self.parse_infix_notation(expression)
        for ope in self.convert(infix_expression):
            # Operands.
            if ope in self.operands:
                stack.append(self.operands[ope])
                stackposition += 1
            elif is_number(ope):
                stack.append(float(ope))
                stackposition += 1
            # Special case distance.
            elif 'd_from' in ope:
                stack.append(self.operators['d_from']['function'](ope))
                stackposition += 1
            # Special case name and namenot.
            elif 'name' in ope:
                stack.append(self.operators['name']['function'](ope))
                stackposition += 1
            # Operators.
            elif ope in self.operators:
                stack[stackposition] = self.operators[ope]['function'](stack[stackposition - 1], stack[stackposition])
                del stack[stackposition - 1]
                stackposition -= 1
        return stack[0]
