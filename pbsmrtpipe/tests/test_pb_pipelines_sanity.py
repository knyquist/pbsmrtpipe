import json
import pprint
import unittest
import logging

import pbsmrtpipe.loader as L
import pbsmrtpipe.graph.bgraph as BU
from pbsmrtpipe.pb_io import (pipeline_template_to_dict,
                              write_pipeline_template_to_avro,
                              load_pipeline_template_from_avro)
from pbsmrtpipe.schemas import validate_pipeline_template

from base import get_temp_file

log = logging.getLogger(__name__)


class TestPipelineSanity(unittest.TestCase):

    def test_all_sane(self):
        """Test that all pipelines are well defined"""
        errors = []
        rtasks, rfiles_types, chunk_operators, pipelines = L.load_all()

        for pipeline_id, pipeline in pipelines.items():
            emsg = "Pipeline {p} is not valid.".format(p=pipeline_id)
            log.debug("Checking Sanity of registered Pipeline {i}".format(i=pipeline_id))
            log.info(pipeline_id)
            log.debug(pipeline)
            try:
                # Validate with Avro
                d = pipeline_template_to_dict(pipeline, rtasks)
                _ = validate_pipeline_template(d)
                name = pipeline_id + "_pipeline_template.avro"
                output_file = get_temp_file(suffix=name)
                log.info("{p} converted to avro successfully".format(p=pipeline_id))

                bg = BU.binding_strs_to_binding_graph(rtasks, pipeline.all_bindings)
                BU.validate_binding_graph_integrity(bg)

                # pprint.pprint(d)

                # for debugging purposes
                output_json = output_file.replace(".avro", '.json')
                log.info("writing pipeline to {p}".format(p=output_json))
                with open(output_json, 'w') as j:
                    j.write(json.dumps(d, sort_keys=True, indent=4))

                log.info("writing pipeline template to {o}".format(o=output_file))

                # Test writing to avro if the pipeline is actually valid
                write_pipeline_template_to_avro(pipeline, rtasks, output_file)
                log.info("Pipeline {p} is valid.".format(p=pipeline_id))

                log.info("Loading avro {i} from {p}".format(i=pipeline_id, p=output_file))
                pipeline_d = load_pipeline_template_from_avro(output_file)
                self.assertIsInstance(pipeline_d, dict)

            except Exception as e:
                m = emsg + "Error " + e.message
                log.error(m)
                errors.append(emsg)
                log.error(emsg)
                log.error(e)

        msg = "\n".join(errors) if errors else ""
        self.assertEqual([], errors, msg)
