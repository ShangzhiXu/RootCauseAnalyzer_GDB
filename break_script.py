import subprocess
import sys
from time import sleep

import gdb
import re
import json
import argparse
import logging
import threading
from abc import ABC, abstractmethod

# gdb -batch -x breakpoint.py ./target
CALL_INSTRUCTION_REGEX = re.compile(r'\bcall\b')
RETURN_INSTRUCTION_REGEX = re.compile(r'\bret\w*\b')
LEA_INSTRUCTION_REGEX = re.compile(r'\blea\b')
"""
TYPE_CODE_ARRAY = 2
TYPE_CODE_BITSTRING = -1
TYPE_CODE_BOOL = 21
TYPE_CODE_CHAR = 20
TYPE_CODE_COMPLEX = 22
TYPE_CODE_DECFLOAT = 25
TYPE_CODE_ENUM = 5
TYPE_CODE_ERROR = 14
TYPE_CODE_FIXED_POINT = 29
TYPE_CODE_FLAGS = 6
TYPE_CODE_FLT = 9
TYPE_CODE_FUNC = 7
TYPE_CODE_INT = 8
TYPE_CODE_INTERNAL_FUNCTION = 27
TYPE_CODE_MEMBERPTR = 17
TYPE_CODE_METHOD = 15
TYPE_CODE_METHODPTR = 16
TYPE_CODE_MODULE = 26
TYPE_CODE_NAMELIST = 30
TYPE_CODE_NAMESPACE = 24
TYPE_CODE_PTR = 1
TYPE_CODE_RANGE = 12
TYPE_CODE_REF = 18
TYPE_CODE_RVALUE_REF = 19
TYPE_CODE_SET = 11
TYPE_CODE_STRING = 13
TYPE_CODE_STRUCT = 3
TYPE_CODE_TYPEDEF = 23
TYPE_CODE_UNION = 4
TYPE_CODE_VOID = 10
TYPE_CODE_XMETHOD = 28
"""

# Create handlers
file_handler = logging.FileHandler('debugger.log', mode='w')
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)

# Create formatters
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_formatter = logging.Formatter('%(levelname)s - %(message)s')

# Add formatters to handlers
file_handler.setFormatter(file_formatter)
console_handler.setFormatter(console_formatter)

# Get the root logger and set level
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)


class DebuggerState:
    def __init__(self):
        self.function_data = {
            "breakpoints": []
        }
        self.should_continue = False
        # Tracks call counts: {caller: {callee: count}}
        self.call_counts = {}
        self.input_data = {}
        self.debugLevel = 0
        self.input_path = ""
        self.output_path = ""


debugger_state = DebuggerState()

class BreakpointHandler(ABC, gdb.Breakpoint):
    """
    Abstract base class for GDB breakpoint handlers.
    Defines the interface and shared functionality for all breakpoint handlers.
    """

    def __init__(self, address, function_name=None, caller_function=None):
        """
        Initializes the breakpoint handler.

        Args:
            address (str): The memory address or symbol where the breakpoint is set.
            function_name (str, optional): The name of the function associated with the breakpoint.
            caller_function (str, optional): The name of the caller function, if applicable.
        """
        # Ensure gdb.Breakpoint is the first base class for proper initialization
        super(BreakpointHandler, self).__init__(f"*{address}", gdb.BP_BREAKPOINT, internal=True)
        self.address = address
        self.function_name = function_name
        self.caller_function = caller_function

    @abstractmethod
    def stop(self):
        """
        Abstract method called when the breakpoint is hit.
        Must be implemented by all subclasses.
        """
        pass


    def increment_call_count(self, increment=True):

        """
        Increments and retrieves the current call count for a specific function call.

        Returns:
            tuple: (current_count, total_times_called)
        """
        if self.caller_function:
            if self.caller_function not in debugger_state.input_data:
                return 0, 0
            if self.caller_function not in debugger_state.call_counts:
                debugger_state.call_counts[self.caller_function] = {}
            if self.function_name not in debugger_state.call_counts[self.caller_function]:
                debugger_state.call_counts[self.caller_function][self.function_name] = 0

            if increment:
                debugger_state.call_counts[self.caller_function][self.function_name] += 1
            current_count = debugger_state.call_counts[self.caller_function][self.function_name]

            total_times_called = 0
            if self.function_name in debugger_state.input_data[self.caller_function]['calls']:
                total_times_called = debugger_state.input_data[self.caller_function]['calls'][self.function_name]
            logging.debug(f"{self.caller_function} called {self.function_name} {current_count} times, total {total_times_called} times.")

            return current_count, total_times_called
        return 0, 0


    def collect_common_data(self, frame, state):
        """
        Collects common debugging data such as local variables, global variables, member variables, and arguments.

        Args:
            frame (gdb.Frame): The current GDB frame.

        Returns:
            dict: A dictionary containing the collected debugging data.
        """
        break_point = {
            "location": self.caller_function,
            "state": state,
            "local_vars": self.get_local_var(frame),
            "global_vars": self.get_global_var(frame),
            "member_vars": self.get_member_var(frame),
            "arguments": self.get_arguments(frame),
            "line": frame.find_sal().line
        }
        return break_point

    def get_local_var(self, frame):
        local_vars = {}
        try:
            block = frame.block()
        except Exception as e:
            logging.error(f"Failed to get frame block: {e}")
            return local_vars

        for symbol in block:
            if symbol.is_variable:
                value = frame.read_var(symbol)
                # use parse_and_eval to get value
                formatted_value = format_value(value)
                # str_value = str(formatted_value)
                # str_value = str_value.replace("\\000", "")
                local_vars[symbol.name] = formatted_value

        return local_vars

    def get_global_var(self, frame):
        global_vars = {}
        try:
            global_block = frame.block()
        except Exception as e:
            logging.error(f"Failed to get frame block: {e}")
            return global_vars
        while global_block and not global_block.is_global:
            global_block = global_block.superblock

        if global_block and global_block.is_global:
            global_symbols = [sym for sym in global_block if sym.is_variable and not sym.is_argument]
            for sym in global_symbols:
                value = sym.value(frame)
                formatted_value = format_value(value)
                # str_value = str(formatted_value)
                # str_value = str_value.replace("\\000", "")
                global_vars[sym.name] = formatted_value

        else:
            logging.debug("  <No global variables found or unable to access global block>")
        return global_vars

    def get_member_var(self, frame):
        this_symbol = None
        try:
            block = frame.block()
        except Exception as e:
            logging.error(f"Failed to get frame block: {e}")
            return {}
        member_vars = {}
        while block:
            for symbol in block:
                # Look for the 'this' pointer which is typical in C++ member functions
                if symbol.name == 'this' and symbol.is_argument:
                    this_symbol = symbol
                    break
            if this_symbol:
                break
            block = block.superblock

        if this_symbol:
            this_value = frame.read_var(this_symbol)
            formatted_this_value = format_value(this_value)
            # str_value = str(formatted_this_value)
            # str_value = str_value.replace("\\000", "")
            member_vars["this"] = formatted_this_value

        return member_vars

    def get_arguments(self, frame):
        arguments = {}
        try:
            block = frame.block()
        except Exception as e:
            logging.error(f"Failed to get frame block: {e}")
            return arguments

        # Traverse the block hierarchy to find function arguments
        while block:
            for symbol in block:
                if symbol.is_argument:  # Check if the symbol is an argument

                    arg_value = frame.read_var(symbol)
                    formatted_arg = format_value(arg_value)
                    # str_value = str(formatted_arg)
                    # str_value = str_value.replace("\\000", "")
                    arguments[symbol.name] = formatted_arg

            # Move up in the block hierarchy
            block = block.superblock
        return arguments

class BreakAtCallHandler(BreakpointHandler):

    def stop(self):
        logging.debug(f"Stopped at {self.function_name} at function start, called from {self.caller_function}.")
        current_count, total_times_called = self.increment_call_count()
        logging.info(f"Function {self.function_name} called {current_count} times, total {total_times_called} times.")
        if current_count < total_times_called:
            # go continue
            gdb.post_event(lambda: post_callback(self.function_name))
            return True

        frame = gdb.selected_frame()
        sal = frame.find_sal()
        line_num = sal.line
        file_name = "unknown"
        try:
            file_name = sal.symtab.filename
        except Exception as e:
            pass
        logging.debug(f"SAL: {sal} Line: {line_num} File: {file_name}")

        break_point = self.collect_common_data(frame, "before function call of " + self.function_name)

        logging.info("[Local Variables]:")
        local_vars = self.get_local_var(frame)
        for key, value in local_vars.items():
            logging.info(f"  {key} = {json.dumps(value, indent=4)}")
        break_point["local_vars"] = local_vars


        logging.info("[Global Variables]:")
        global_vars = self.get_global_var(frame)
        for key, value in global_vars.items():
            logging.info(f"  {key} = {json.dumps(value, indent=4)}")
        break_point["global_vars"] = global_vars

        # Check for member variables if the current function has a 'this' pointer
        logging.info("[Member Variables]:")
        member_vars = self.get_member_var(frame)
        for key, value in member_vars.items():
            logging.info(f"  {key} = {json.dumps(value,indent=4)}")
        break_point["member_vars"] = member_vars

        # output arguments
        logging.info("[Arguments]:")
        arguments = self.get_arguments(frame)
        for key, value in arguments.items():
            logging.info(f"  {key} = {json.dumps(value, indent=4)}")
        break_point["arguments"] = arguments

        debugger_state.function_data["breakpoints"].append(break_point)
        # step into the next function
        gdb.post_event(lambda: post_callback(self.function_name))

        if debug:
            logging.info(f"Scheduled '{self.function_name}' step request via gdb.post_event.")

        return True


class BreakAtFunctionStartHandler(BreakpointHandler):

    def stop(self):
        logging.debug(f"Stopped at {self.function_name} at function start, called from {self.caller_function}.")

        try:
            disasm = gdb.execute(f"disassemble {self.function_name}", to_string=True)
        except Exception as e:
            logging.error(f"Failed to disassemble {self.function_name}: {e}")
            return

        set_breakpoints(disasm, self.function_name, self.caller_function)

        # step into the next function
        gdb.post_event(lambda: post_callback(self.function_name))

        return True


class BreakAtReturnHandler(BreakpointHandler):

    def execute_continue(self):
        try:
            gdb.execute("continue")
            logging.debug("Continued")
        except Exception as e:
            logging.error(f"Failed to continue: {e}")
        return

    def stop(self):
        logging.debug(f"Stopped at {self.function_name} at function return, returning to {self.caller_function}.")
        if self.caller_function:
            current_count, total_times_called = self.increment_call_count(increment=False)
            logging.info(
                f"Function {self.function_name} called {current_count} times, total {total_times_called} times.")
            if current_count < total_times_called:
                # go continue
                gdb.post_event(lambda: post_callback("ret"))
                return True

        frame = gdb.selected_frame()
        sal = frame.find_sal()
        line_num = sal.line
        file_name = "unknown"
        try:
            file_name = sal.symtab.filename
        except Exception as e:
            pass
        logging.debug(f"SAL: {sal} Line: {line_num} File: {file_name}")

        break_point = self.collect_common_data(frame, "before function return of " + self.function_name)

        # print all local variables
        logging.info("[Local Variables]:")
        local_vars = self.get_local_var(frame)
        break_point["local_vars"] = local_vars

        # print all global variables
        logging.info("[Global Variables]:")
        global_vars = self.get_global_var(frame)
        break_point["global_vars"] = global_vars

        # in cpp, we can also print out the member variables of the current object
        # if the current function is a member function
        # Check for member variables if the current function has a 'this' pointer
        logging.info("[Member Variables]:")
        member_vars = self.get_member_var(frame)
        break_point["member_vars"] = member_vars

        # output arguments
        logging.info("[Arguments]:")
        arguments = self.get_arguments(frame)
        break_point["arguments"] = arguments

        debugger_state.function_data["breakpoints"].append(break_point)

        # step into the next function
        gdb.post_event(lambda: post_callback("ret"))

        return True


def on_exit_handler(event):
    try:
        with open(debugger_state.output_path, 'w') as f:
            json.dump(debugger_state.function_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to write output data: {e}")


# utility functions
def set_gdb_print_options():
    try:
        gdb.execute("set python print-stack full", to_string=True)
        gdb.execute("set print repeats unlimited", to_string=True)
        gdb.execute("set print array on", to_string=True)
        gdb.execute("set pagination off")  # Disable pagination to simplify output
    except Exception as e:
        logging.error(f"Failed to set GDB print options: {e}")


def unwrap_value(value):
    """
    Unwraps typedefs and references to get the underlying value.

    Args:
        value: The GDB value to unwrap.

    Returns:
        The unwrapped GDB value.
    """
    if not isinstance(value, str):
        return value
    while value.type.code == gdb.TYPE_CODE_TYPEDEF:
        value = value.cast(value.type.target())
    if value.type.code in (gdb.TYPE_CODE_REF, gdb.TYPE_CODE_RVALUE_REF):
        value = value.referenced_value()
    return value


def format_struct_union(value, current_depth, max_depth):
    """
    Formats struct and union types.

    Args:
        value: The GDB struct or union value.
        current_depth (int): Current recursion depth.
        max_depth (int): Maximum allowed recursion depth.

    Returns:
        str
    """
    fields = {}

    num_fields = len(value.type.fields())  # get the number of fields
    for field in value.type.fields():
        field_name = field.name
        field_value = ""
        try:
            field_value = value[field_name]
        except Exception as e:
            logging.error(f"Failed to get field value: {e}")
            fields[field_name] = "<unavailable>"
            continue
        formatted_field = format_value(field_value, current_depth, max_depth)
        fields[field_name] = formatted_field

    return fields


def format_array(value, current_depth, max_depth):
    """
    Formats array types.

    Args:
        value: The GDB array value.
        current_depth (int): Current recursion depth.
        max_depth (int): Maximum allowed recursion depth.

    Returns:
        str: The formatted array string.
    """

    elements = {}
    num_elements = value.type.sizeof // value.type.target().sizeof

    if value.type.target().code == gdb.TYPE_CODE_INT:
        # return the length of array, to show the developer
        # the possibility of the overflow
        try:
            str_value = str(value)
            str_value = str_value.replace("\\000", "")
            return str_value
        except Exception as e:
            logging.error(f"Failed to get string value: {e}")
            return "<unavailable>"

    elif value.type.target().code == gdb.TYPE_CODE_CHAR:
        # if the array is an array of characters, print out the string
        try:
            str_value = str(value)
            str_value = str_value.replace("\\000", "")
            return str_value
        except Exception as e:
            logging.error(f"Failed to get string value: {e}")
            return "<unavailable>"
    else:
        # if the array is not an array of integers, contain other types as elements
        for i in range(0, num_elements):
            elem = value[i]
            # if the element is a pointer, or an array, or a struct, or a union, or a typedef, or a function
            if (elem.type.code == gdb.TYPE_CODE_PTR
                    or elem.type.code == gdb.TYPE_CODE_ARRAY
                    or elem.type.code == gdb.TYPE_CODE_STRUCT
                    or elem.type.code == gdb.TYPE_CODE_UNION
                    or elem.type.code == gdb.TYPE_CODE_TYPEDEF
                    or elem.type.code == gdb.TYPE_CODE_FUNC):
                formatted_elem = format_value(elem, current_depth + 1, max_depth)
            else:
                formatted_elem = elem

            elements[i] = formatted_elem

        return elements



def format_pointer(value, current_depth, max_depth, layers):
    """
    Formats pointer types.

    Args:
        value: The GDB pointer value.
        current_depth (int): Current recursion depth.
        max_depth (int): Maximum allowed recursion depth.

    Returns:
        str: The formatted pointer string.
    """
    temp_value = unwrap_value(value)
    # handle pointers, loop until the value is not a pointer or the max depth is reached
    while (temp_value.type.code == gdb.TYPE_CODE_PTR) \
            and current_depth < max_depth:
        temp_value = unwrap_value(temp_value)
        logging.debug(f"[Pointer] {temp_value} [Type] {temp_value.type.name} ({temp_value.type.code})")
        if temp_value.type.target().code == gdb.TYPE_CODE_INT or \
                temp_value.type.target().code == gdb.TYPE_CODE_FLT:
            elements = []

            element_size = temp_value.type.target().sizeof
            address = int(temp_value)

            logging.debug(f"[Pointer] {temp_value} [Address] {address} [Size] {element_size}")
            max_elements = 20
            if temp_value.type.target().code == gdb.TYPE_CODE_INT or \
                    temp_value.type.target().code == gdb.TYPE_CODE_FLT:
                # print out according to it's size, if is a pointer, print out first 10 elements
                # if is a int or float, print out the value
                if (element_size == 4 or element_size == 8):
                    # if the size is 4 or 8 bytes, print out the value
                    str_value = str(temp_value.dereference())
                    str_value = str_value.replace("\\000", "")
                    elements.append(str_value)
                    return layers, "".join(elements)
                else:
                    # if the size is not 4 or 8 bytes, print out the first 10 elements
                    elem = ""
                    i = 0
                    while len(elements) < max_elements:
                        try:
                            elem = (temp_value + i).dereference()
                            elem_int = int(elem)
                            elem_str = str(elem)
                            elem_str = elem_str.replace("\\000", "")
                            elements.append(elem_str)
                            if elem_int == 0:
                                # Stop when the first zero occurs
                                break
                            if elem_str == "\\000":
                                break
                            if elem_str == "\000":
                                break
                            i += 1
                        except Exception as e:
                            elements.append("<unavailable>")
                            logging.error(f"[Error] Failed to dereference pointer: {e}")
                            break
                    return layers, "[" + ", ".join(elements) + "]"

        elif temp_value.type.target().code == gdb.TYPE_CODE_VOID:
            layers.append(f"(void*){temp_value}")
            break
        elif temp_value.type.target().code == gdb.TYPE_CODE_CHAR:
            layers.append(temp_value.string())
            break

        if temp_value == 0:
            layers.append("NULL")
            break

        layers.append(format_value(temp_value.dereference(),current_depth, max_depth))
        try:
            temp_value = temp_value.dereference()
            current_depth += 1
        except Exception as e:
            layers.append("<invalid pointer>")
            logging.error(f"[Error] Failed to dereference pointer: {e}")
            break

    return layers, temp_value


def format_value(value, current_depth=0, max_depth=100):
    """
    Recursively formats a GDB value into a readable string.

    Args:
        value: The GDB value to format.
        current_depth (int): Current recursion depth.
        max_depth (int): Maximum allowed recursion depth.

    Returns:
        str: The formatted string representation of the value.
    """
    if current_depth > max_depth:
        return "<max recursion depth reached>"

    # print out value and its type
    layers = []
    depth = current_depth
    type_code = value.type.code
    type_name = "unknown"
    value = unwrap_value(value)
    layers, value = format_pointer(value, current_depth, max_depth, layers)
    if not isinstance(value, str):
        type_code = value.type.code
        type_name = value.type.name

    # handle arrays, structs, unions, typedefs
    # for structs, unions, and typedefs, recursively print out their fields
    if (type_code == gdb.TYPE_CODE_STRUCT
            or type_code == gdb.TYPE_CODE_UNION):

        fields = format_struct_union(value, depth, max_depth)
        #print("Value is a struct or union, returning ", json.dumps(fields, indent=4), type_code)
        return fields
    # for arrays, try to print out the length
    # or the elements if the array contains elems of complex types
    elif type_code == gdb.TYPE_CODE_ARRAY:
        array = format_array(value, depth, max_depth)
        #print (f"Value is an array, returning {json.dumps(array, indent=4)}", type_code)
        return array
    elif type_code == gdb.TYPE_CODE_TYPEDEF:
        # for typedefs, extract the underlying type
        underlying_type = value.type.strip_typedefs()
        #print(f"Value is a typedef, returning {underlying_type}", type_code)
        return format_value(value.cast(underlying_type), depth, max_depth)
    else:
        try:
            str_value = str(value)
            str_value = str_value.replace("\\000", "")
            # print("Value to return is: ", str_value, type_code)
            return str_value
        except  Exception as e:
            logging.error(f"Failed to get string value: {e}")
            return "<unavailable>"




def set_breakpoints(disasm, current_function_name, caller_function_name=None):
    # logging.debug(f"[Disassembly] {disasm}")
    call_instructions_number = 0
    function_start_instructions_number = 0
    return_instructions_number = 0
    breakpoints = []

    for line in disasm.splitlines():
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        addr = parts[0]
        instr = parts[2]

        # edge case: call instruction with PLT
        match = re.search(r'call\s+.*@plt', line)

        # 0x0000555555557361 <+376>:   call   0x5555555570e0 <_Unwind_Resume@plt>
        if match:
            called_function_name = parts[-1].strip("<").strip(">").split("@")[0].strip("(").strip(")")
        else:
            called_function_name = parts[-1].strip("<").strip(">").strip("(").strip(")")
        called_function_addr = parts[-2]

        if CALL_INSTRUCTION_REGEX.search(instr) or LEA_INSTRUCTION_REGEX.search(instr):
            addr_clean = addr.rstrip(':')

            if called_function_name not in debugger_state.input_data:
                logging.debug(f"Function {called_function_name} not found in input data.")
                continue
            logging.debug(f"[Call] {line}")
            # if there is not a breakpoint set at this address, set one
            if not any(bp.location == f"*{addr_clean}" for bp in gdb.breakpoints()):
                BreakAtCallHandler(addr_clean, called_function_name, current_function_name)
                call_instructions_number += 1
                breakpoints.append(called_function_name)

            # also break at the start of the function
            if not any(bp.location == f"*{called_function_addr}" for bp in gdb.breakpoints()):
                BreakAtFunctionStartHandler(called_function_addr, called_function_name, current_function_name)
                function_start_instructions_number += 1
                breakpoints.append(called_function_name)


        elif RETURN_INSTRUCTION_REGEX.search(instr):
            addr_clean = addr.rstrip(':')
            if current_function_name not in debugger_state.input_data:
                continue
            logging.debug(f"[Return] {line}")

            # if there is not a breakpoint set at this address, set one
            if not any(bp.location == f"*{addr_clean}" for bp in gdb.breakpoints()):
                BreakAtReturnHandler(addr_clean, current_function_name, caller_function_name)
                return_instructions_number += 1
                breakpoints.append("ret")

    if debug_break or debug:
        for bp in breakpoints:
            logging.debug(f"[Breakpoint] {bp}")


def step_into_next(breakpoint_type):
    """
    step into the next function, or step out of the current function
    in the next function, set breakpoints at call instructions and return instructions
    """
    try:
        gdb.execute("step", from_tty=False, to_string=True)
        logging.debug(f"Stepped into the next function.")
        if breakpoint_type != "ret":
            try:
                disasm = gdb.execute(f"disassemble {breakpoint_type}", to_string=True)
            except Exception as e:
                logging.error(f"Failed to disassemble {breakpoint_type}: {e}")
                return

            set_breakpoints(disasm, breakpoint_type)
    except Exception as e:
        logging.error(f"Failed to step into the next function: {e}")
    return


def delete_breakpoints():
    # if there are breakpoints no longer needed, delete them
    for bp in gdb.breakpoints():
        if bp.is_internal:
            bp.delete()


def post_callback_continue():
    try:
        gdb.execute("continue")
    except Exception as e:
        logging.error(f"Failed to continue: {e}")


def post_callback(breakpoint_type):
    try:
        gdb.post_event(lambda: post_callback_continue())
    except Exception as e:
        logging.error(f"Failed to schedule continue: {e}")
    return


def load_input_data(json_file_path):
    """
    Loads input data from a JSON file.

    Args:
        json_file_path (str): The path to the JSON file containing input data.

    Returns:
        dict: The parsed input data as a Python dictionary.
    """
    try:
        with open(json_file_path, 'r') as f:
            input_data = json.load(f)
        return input_data
    except FileNotFoundError:
        logging.error(f"Input JSON file not found: {json_file_path}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"JSON decoding error in {json_file_path}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error loading input data: {e}")
        raise


def process_input_data(input_data):
    """
    Processes the input_data to map calls to times_called for easier access.

    Args:
        input_data (dict): The raw input_data loaded from JSON.

    Returns:
        dict: Processed input_data with calls mapped to times_called.
    """
    processed_data = {}
    for func, details in input_data.items():
        calls = details.get('calls', [])
        times_called = details.get('times_called', [])
        # Map each call to its corresponding times_called
        call_times_map = {}
        for i, call in enumerate(calls):
            if i < len(times_called):
                call_times_map[call] = times_called[i]
            else:
                call_times_map[call] = 1  # Default to 1 if not specified
        processed_data[func] = {
            'local_vars': details.get('local_vars', []),
            'calls': call_times_map
        }
    return processed_data


def load_config(config_file_path="config.json"):
    """
    Loads configuration data from a JSON file.

    Args:
        config_file_path (str): The path to the configuration JSON file.

    Returns:
        dict: The parsed configuration data as a Python dictionary.
    """
    try:
        with open(config_file_path, 'r') as f:
            config_data = json.load(f)
        return config_data
    except FileNotFoundError:
        logging.error(f"Configuration JSON file not found: {config_file_path}")
        raise
    except json.JSONDecodeError as e:
        logging.error(f"JSON decoding error in {config_file_path}: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error loading configuration data: {e}")
        raise

def initialize():
    global debug
    global debug_break
    global debug_disasm

    config_data = load_config()
    debugger_state.input_path = config_data.get("input", "input.json")
    debugger_state.stdinput_path = config_data.get("stdinput", "input.txt")
    debugger_state.output_path = config_data.get("output", "output.json")
    debugger_state.debugLevel = config_data.get("debugLevel", 0)
    debug = config_data.get("debug", False)
    debug_break = config_data.get("debug_break", False)
    debug_disasm = config_data.get("debug_disasm", False)

    set_gdb_print_options()
    debugger_state.input_data = process_input_data(load_input_data(debugger_state.input_path))
    gdb.events.exited.connect(on_exit_handler)

    try:
        gdb.execute("break _start", to_string=True)
        gdb.execute(f"run < {debugger_state.stdinput_path}", to_string=True)
    except Exception as e:
        logging.error(f"Failed to set breakpoints and run the program: {e}")
        return

    # set breakpoints
    disasm = gdb.execute("disassemble main", to_string=True)
    first_instruction_address = disasm.splitlines()[1].split()[0]  # Extract address
    gdb.execute(f"break *{first_instruction_address}", to_string=True)
    gdb.execute("continue")
    set_breakpoints(disasm, "main", "_start")
    # continue to the next breakpoint
    gdb.execute("continue")



initialize()
