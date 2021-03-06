#
# This file is part of LUNA.
#
""" Utilities for building USB descriptors into gateware. """

from nmigen                            import Signal, Module, Elaboratable
from usb_protocol.emitters.descriptors import DeviceDescriptorCollection
from ..stream                          import USBInStreamInterface
from ...stream.generator               import ConstantStreamGenerator


class USBDescriptorStreamGenerator(ConstantStreamGenerator):
    """ Specialized stream generator for generating USB descriptor constants. """

    def __init__(self, data):
        """
        Parameters:
            descriptor_number -- The descriptor number represented.
            data              -- The raw bytes (or equivalent) for the descriptor.
        """

        # Always create USB descriptors in the USB domain; always have a maximum length field that can
        # be up to 16 bits wide, and always use USBInStream's. These allow us to tie easily to our request
        # handlers.
        super().__init__(data, domain="usb", stream_type=USBInStreamInterface, max_length_width=16)



class GetDescriptorHandler(Elaboratable):
    """ Gateware that handles responding to GetDescriptor requests.

    Currently does not support descriptors in multiple languages.

    I/O port:
        I: value[16]  -- The value field associated with the Get Descriptor request.
                         Contains the descriptor type and index.
        I: length[16] -- The length field associated with the Get Descriptor request.
                         Determines the maximum amount allowed in a response.

        I: start      -- Strobe that indicates when a descriptor should be transmitted.

        *: tx         -- The USBInStreamInterface that streams our descriptor data.
        O: stall      -- Pulsed if a STALL handshake should be generated, instead of a response.
    """

    def __init__(self, descriptor_collection: DeviceDescriptorCollection):
        """
        Parameteres:
            descriptor_collection -- The DeviceDescriptorCollection containing the descriptors
                                     to use for this device.
        """

        self._descriptors = descriptor_collection

        #
        # I/O port
        #
        self.value  = Signal(16)
        self.length = Signal(16)

        self.start  = Signal()

        self.tx     = USBInStreamInterface()
        self.stall  = Signal()


    def elaborate(self, platform):
        m = Module()

        # Collection that will store each of our descriptor-generation submodules.
        descriptor_generators = {}

        #
        # Create our constant-stream generators for each of our descriptors.
        #
        for type_number, index, raw_descriptor in self._descriptors:

            # Create the generator...
            generator = USBDescriptorStreamGenerator(raw_descriptor)
            descriptor_generators[(type_number, index)] = generator

            # ... and attach it to this module.
            m.submodules += generator


        #
        # Connect up each of our generators.
        #

        with m.Switch(self.value):

            # Generate a conditional interconnect for each of our items.
            for (type_number, index), generator in descriptor_generators.items():

                # If the value matches the given type number...
                with m.Case(type_number << 8 | index):

                    # ... connect the relevant generator to our output.
                    m.d.comb += [
                        generator.stream      .attach(self.tx),
                        generator.start       .eq(self.start),
                        generator.max_length  .eq(self.length)
                    ]

            # If none of our descriptors match, stall any request that comes in.
            with m.Case():
                m.d.comb += self.stall.eq(self.start)


        return m
